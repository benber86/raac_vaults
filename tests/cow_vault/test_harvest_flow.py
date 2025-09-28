import boa
import pytest
from boa.contracts.abi.abi_contract import ABIContractFactory
from boa.util.abi import abi_encode
from eth_utils import function_signature_to_4byte_selector

from src import raac_vault, strategy
from src.harvesters import cow_harvester
from tests.conftest import PYUSD_POOL_NAME, USDC_POOL_NAME
from tests.utils.abis import COMPOSABLE_COW_ABI
from tests.utils.constants import CRVUSD_POOLS, CURVE_TRICRV_POOL
from tests.utils.harvest_calculations import (
    approx,
    calc_expected_fees,
    calc_expected_lp_tokens,
)


@pytest.mark.parametrize("pool_name", [PYUSD_POOL_NAME, USDC_POOL_NAME])
def test_cow_harvester_workflow(
    cow_vault_list,
    funded_accounts,
    pool_list,
    crvusd_token,
    crvusd_minter,
    crv_token,
    cvx_token,
    treasury,
    add_liquidity_hook,
    harvest_manager,
    pool_name,
):
    crvusd_pool = pool_list[pool_name]
    vault_addr, strategy_addr, harvester_addr = cow_vault_list[pool_name]
    user = funded_accounts[0]

    vault_contract = raac_vault.at(vault_addr)
    harvester_contract = cow_harvester.at(harvester_addr)

    # User deposits into vault
    user_lp_balance = crvusd_pool.balanceOf(user)
    deposit_amount = user_lp_balance // 2

    with boa.env.prank(user):
        crvusd_pool.approve(vault_addr, deposit_amount)
        vault_contract.deposit(deposit_amount, user)

    initial_total_assets = vault_contract.totalAssets()
    initial_treasury_crvusd = crvusd_token.balanceOf(treasury)

    boa.env.time_travel(seconds=86400 * 2)

    # First harvest - creates orders but no immediate rewards
    target_hook_calldata = _prepare_target_hook_calldata(
        crvusd_pool.address, crvusd_token.address, pool_name
    )

    buy_amounts = [int(1 * 1e18), int(5 * 1e18)]  # Minimum crvUSD expected

    with boa.env.prank(harvest_manager):
        vault_contract.harvest(
            user,  # caller
            0,  # min_amount_out
            [],  # extra_rewards
            b"",  # reward_hook_calldata (not used)
            target_hook_calldata,
            abi_encode("(uint256[])", [buy_amounts]),
        )

    # Check that no treasury fees paid yet (no crvUSD available)
    intermediate_treasury_crvusd = crvusd_token.balanceOf(treasury)
    assert (
        intermediate_treasury_crvusd == initial_treasury_crvusd
    ), "Treasury should not receive fees on first harvest (no crvUSD available)"

    # Check that orders were created
    crv_order_exists, crv_order_info = harvester_contract.get_order_info(
        crv_token.address
    )
    cvx_order_exists, cvx_order_info = harvester_contract.get_order_info(
        cvx_token.address
    )

    assert crv_order_exists, "CRV order should be created"
    assert cvx_order_exists, "CVX order should be created"
    assert crv_order_info.sell_amount > 0, "CRV order should have sell amount"
    assert cvx_order_info.sell_amount > 0, "CVX order should have sell amount"
    # Check that no caller fee paid yet (no crvUSD available)
    assert (
        vault_contract.totalAssets() <= initial_total_assets
    ), "Assets should not increase on first harvest"

    # Simulate CoW searcher execution - remove CRV/CVX and add crvUSD
    crv_balance = crv_token.balanceOf(harvester_addr)
    cvx_balance = cvx_token.balanceOf(harvester_addr)

    expected_crvusd = int(10_000 * 1e18)

    with boa.env.prank(harvester_addr):
        crv_token.transfer(boa.env.generate_address(), crv_balance)
        cvx_token.transfer(boa.env.generate_address(), cvx_balance)

    with boa.env.prank(crvusd_minter):
        crvusd_token.mint(harvester_addr, expected_crvusd)

    # Wait for more rewards and do second harvest
    boa.env.time_travel(seconds=86400 * 7)

    # Calculate expected fees based on available crvUSD
    gross_harvest_crvusd = (
        expected_crvusd  # We know exactly how much crvUSD is available
    )
    platform_fee_bps = strategy.at(strategy_addr).platform_fee()
    caller_fee_bps = strategy.at(strategy_addr).caller_fee()

    expected_platform_fees, expected_caller_fees, expected_net_harvest = (
        calc_expected_fees(
            gross_harvest_crvusd, platform_fee_bps, caller_fee_bps
        )
    )

    initial_user_crvusd = crvusd_token.balanceOf(user)
    initial_vault_assets = vault_contract.totalAssets()

    print(f"Expected gross harvest: {gross_harvest_crvusd / 1e18:.6f} crvUSD")
    print(
        f"Expected platform fees: {expected_platform_fees / 1e18:.6f} crvUSD"
    )
    print(f"Expected caller fees: {expected_caller_fees / 1e18:.6f} crvUSD")
    print(f"Expected net harvest: {expected_net_harvest / 1e18:.6f} crvUSD")
    print(f"Initial total assets: {initial_vault_assets / 1e18:.6f} crvUSD")

    with boa.env.prank(harvest_manager):
        vault_contract.harvest(
            user,  # caller
            0,  # min_amount_out
            [],  # extra_rewards (empty - just CRV+CVX)
            b"",  # reward_hook_calldata (not used)
            target_hook_calldata,
            abi_encode("(uint256[])", [buy_amounts]),  # harvester_calldata
        )

    # Check the second harvest results
    final_user_crvusd = crvusd_token.balanceOf(user)
    final_vault_assets = vault_contract.totalAssets()
    final_treasury_crvusd = crvusd_token.balanceOf(treasury)

    # Calculate actual amounts received
    actual_treasury_fees = final_treasury_crvusd - initial_treasury_crvusd
    actual_caller_fees = final_user_crvusd - initial_user_crvusd
    actual_vault_increase = final_vault_assets - initial_vault_assets

    print(f"Final total assets: {final_vault_assets / 1e18:.6f} crvUSD")
    print(f"Actual treasury fees: {actual_treasury_fees / 1e18:.6f} crvUSD")
    print(f"Actual caller fees: {actual_caller_fees / 1e18:.6f} crvUSD")
    print(
        f"Actual vault increase: {actual_vault_increase / 1e18:.6f} LP tokens"
    )

    # Calculate expected vault increase in LP token terms
    expected_vault_increase_lp = calc_expected_lp_tokens(
        crvusd_pool,
        harvester_addr,
        crvusd_token,
        crvusd_minter,
        expected_net_harvest,
        pool_name,
    )

    print(
        f"Expected vault increase: {expected_vault_increase_lp / 1e18:.6f} LP tokens"
    )

    # Verify precise fee distributions (using 0.1% tolerance)
    assert approx(
        actual_treasury_fees, expected_platform_fees, 1e-3
    ), f"Treasury fees mismatch: got {actual_treasury_fees}, expected {expected_platform_fees}"

    assert approx(
        actual_caller_fees, expected_caller_fees, 1e-3
    ), f"Caller fees mismatch: got {actual_caller_fees}, expected {expected_caller_fees}"

    # The vault increase should match expected LP tokens from adding net harvest as liquidity
    assert approx(
        actual_vault_increase, expected_vault_increase_lp, 1e-3
    ), f"Vault increase mismatch: got {actual_vault_increase}, expected {expected_vault_increase_lp}"

    # Check that new orders were created with updated amounts
    new_crv_order_exists, new_crv_order_info = (
        harvester_contract.get_order_info(crv_token.address)
    )
    new_cvx_order_exists, new_cvx_order_info = (
        harvester_contract.get_order_info(cvx_token.address)
    )

    assert new_crv_order_exists, "New CRV order should be created"
    assert new_cvx_order_exists, "New CVX order should be created"
    assert (
        new_crv_order_info.last_order_time > crv_order_info.last_order_time
    ), "Order should be updated"


def _prepare_target_hook_calldata(
    pool_address: str, token_address: str, pool_name: str
) -> bytes:

    target_sig = "add_liquidity(address,address,uint256,uint256)"
    target_selector = function_signature_to_4byte_selector(target_sig)
    target_encoded_args = abi_encode(
        "(address,address,uint256,uint256)",
        [
            pool_address,
            token_address,
            CRVUSD_POOLS[pool_name]["crvusd_index"],
            0,
        ],
    )
    return target_selector + target_encoded_args


def test_cow_order_cancellation(
    test_cow_vault, funded_accounts, crvusd_pool, crv_token, harvest_manager
):
    vault_addr, strategy_addr, harvester_addr = test_cow_vault

    vault_contract = raac_vault.at(vault_addr)
    harvester_contract = cow_harvester.at(harvester_addr)

    buy_amounts = [int(100 * 1e18), int(50 * 1e18)]  # Non-zero amounts
    # need a dpsoit for the harvest
    user = funded_accounts[0]
    with boa.env.prank(user):
        crvusd_pool.approve(vault_addr, 10**18)
        vault_contract.deposit(10**18, user)

    with boa.env.prank(harvest_manager):
        vault_contract.harvest(
            harvest_manager,
            0,  # min_amount_out
            [],  # extra_rewards (empty, just CRV+CVX)
            b"",  # reward_hook_calldata
            b"",  # target_hook_calldata
            abi_encode("(uint256[])", [buy_amounts]),  # harvester_calldata
        )

    crv_order_exists, _ = harvester_contract.get_order_info(crv_token.address)
    assert crv_order_exists, "CRV order should be created"

    composable_cow = ABIContractFactory(
        "ComposableCoW", COMPOSABLE_COW_ABI
    ).at(harvester_contract.COMPOSABLE_COW())

    static_input = bytes.fromhex(str(crv_token.address)[2:].zfill(40))[
        :20
    ]  # Convert to bytes20

    conditional_order_params = {
        "handler": harvester_addr,
        "salt": b"\x00" * 32,
        "staticInput": static_input,
    }

    order_hash = composable_cow.hash(
        [
            conditional_order_params["handler"],
            conditional_order_params["salt"],
            conditional_order_params["staticInput"],
        ]
    )

    assert composable_cow.singleOrders(harvester_addr, order_hash)

    with boa.env.prank(harvest_manager):
        harvester_contract.cancel_order(crv_token.address)

    assert not composable_cow.singleOrders(harvester_addr, order_hash)

    assert composable_cow.cabinet(harvester_addr, order_hash) == b"\x00" * 32

    crv_order_exists_after, order_info_after = (
        harvester_contract.get_order_info(crv_token.address)
    )
    assert not crv_order_exists_after, "Order should be cancelled"
    assert order_info_after.last_order_time == 0, "Order info should be reset"

    vault_relayer = harvester_contract.VAULT_RELAYER()
    approval_amount = crv_token.allowance(harvester_addr, vault_relayer)
    assert (
        approval_amount == 0
    ), "Token approval should be revoked after cancellation"


def test_cow_order_expiry(
    test_cow_vault, funded_accounts, crvusd_pool, crv_token, harvest_manager
):
    vault_addr, strategy_addr, harvester_addr = test_cow_vault
    harvester_contract = cow_harvester.at(harvester_addr)

    # Create an order
    buy_amounts = [0, 0]

    with boa.env.prank(CURVE_TRICRV_POOL):
        crv_token.transfer(harvester_addr, int(1000 * 1e18))

    vault_contract = raac_vault.at(vault_addr)
    # need a dpsoit for the harvest
    user = funded_accounts[0]
    with boa.env.prank(user):
        crvusd_pool.approve(vault_addr, 10**18)
        vault_contract.deposit(10**18, user)

    with boa.env.prank(harvest_manager):
        vault_contract.harvest(
            harvest_manager,
            0,  # min_amount_out
            [],  # extra_rewards (empty, just CRV+CVX)
            b"",  # reward_hook_calldata
            b"",  # target_hook_calldata
            abi_encode("(uint256[])", [buy_amounts]),  # harvester_calldata
        )

    boa.env.time_travel(seconds=86400 + 1)
    static_input = bytes.fromhex(str(crv_token.address)[2:].zfill(40))[:20]

    crv_order_exists, crv_order_info = harvester_contract.get_order_info(
        crv_token.address
    )
    assert crv_order_exists, "CRV order should be created"
    assert crv_order_info.sell_amount > 0, "Order should have sell amount"

    with boa.reverts():
        harvester_contract.getTradeableOrder(
            harvester_addr,  # owner
            boa.env.generate_address(),  # sender
            b"\x00" * 32,  # ctx
            static_input,  # static_input
            b"\x00",  # offchain_input
        )


def test_get_tradeable_order_validation(
    test_cow_vault,
    funded_accounts,
    crvusd_pool,
    crv_token,
    cvx_token,
    harvest_manager,
):
    vault_addr, strategy_addr, harvester_addr = test_cow_vault
    harvester_contract = cow_harvester.at(harvester_addr)
    vault_contract = raac_vault.at(vault_addr)

    user = funded_accounts[0]
    with boa.env.prank(user):
        crvusd_pool.approve(vault_addr, 10**18)
        vault_contract.deposit(10**18, user)

    static_input = bytes.fromhex(str(crv_token.address)[2:].zfill(40))[:20]

    with boa.reverts():
        harvester_contract.getTradeableOrder(
            harvester_addr,
            boa.env.generate_address(),
            b"\x00" * 32,
            static_input,
            b"\x00",
        )

    buy_amounts = [int(100 * 1e18), int(50 * 1e18)]
    with boa.env.prank(harvest_manager):
        vault_contract.harvest(
            harvest_manager,
            0,
            [],
            b"",
            b"",
            abi_encode("(uint256[])", [buy_amounts]),
        )

    with boa.env.prank(harvest_manager):
        harvester_contract.cancel_order(crv_token.address)

    with boa.reverts():
        harvester_contract.getTradeableOrder(
            harvester_addr,
            boa.env.generate_address(),
            b"\x00" * 32,
            static_input,
            b"\x00",
        )
