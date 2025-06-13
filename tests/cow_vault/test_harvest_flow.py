import boa
from boa.contracts.abi.abi_contract import ABIContractFactory
from boa.util.abi import abi_encode
from eth_utils import function_signature_to_4byte_selector

from src import raac_vault, strategy
from src.harvesters import cow_harvester
from tests.utils.abis import COMPOSABLE_COW_ABI
from tests.utils.constants import CRVUSD_INDEX_PYUSD_POOL, CURVE_TRICRV_POOL


def test_cow_harvester_workflow(
    test_cow_vault,
    funded_accounts,
    pyusd_crvusd_pool,
    crvusd_token,
    crvusd_minter,
    crv_token,
    cvx_token,
    treasury,
    add_liquidity_hook,
    harvest_manager,
):
    vault_addr, strategy_addr, harvester_addr = test_cow_vault
    user = funded_accounts[0]

    vault_contract = raac_vault.at(vault_addr)
    harvester_contract = cow_harvester.at(harvester_addr)

    # 1. User deposits into vault
    user_lp_balance = pyusd_crvusd_pool.balanceOf(user)
    deposit_amount = user_lp_balance // 2

    with boa.env.prank(user):
        pyusd_crvusd_pool.approve(vault_addr, deposit_amount)
        vault_contract.deposit(deposit_amount, user)

    initial_total_assets = vault_contract.totalAssets()
    initial_treasury_crv = crv_token.balanceOf(treasury)
    initial_treasury_cvx = cvx_token.balanceOf(treasury)

    boa.env.time_travel(seconds=86400 * 2)

    # 1. First harvest - creates orders but no immediate rewards
    target_hook_calldata = _prepare_target_hook_calldata(
        pyusd_crvusd_pool.address, crvusd_token.address
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

    # 2. Check that treasury fees were paid in CRV/CVX
    final_treasury_crv = crv_token.balanceOf(treasury)
    final_treasury_cvx = cvx_token.balanceOf(treasury)

    assert (
        final_treasury_crv > initial_treasury_crv
    ), "Treasury should receive CRV fees"
    assert (
        final_treasury_cvx > initial_treasury_cvx
    ), "Treasury should receive CVX fees"

    # 3. Check that orders were created
    crv_order_exists, crv_order_info = harvester_contract.get_order_info(
        crv_token.address
    )
    cvx_order_exists, cvx_order_info = harvester_contract.get_order_info(
        cvx_token.address
    )

    assert crv_order_exists, "CRV order should be created"
    assert cvx_order_exists, "CVX order should be created"
    assert crv_order_info.sell_amount > 0, "CRV order should have sell amount"
    # we only test for CRV as CVX rewards will usually all have been paid out to treasury

    # 4. Check that no caller fee paid yet (no crvUSD available)
    assert (
        vault_contract.totalAssets() <= initial_total_assets
    ), "Assets should not increase on first harvest"

    # 5. Simulate CoW searcher execution - remove CRV/CVX and add crvUSD
    crv_balance = crv_token.balanceOf(harvester_addr)
    cvx_balance = cvx_token.balanceOf(harvester_addr)

    expected_crvusd = int(10_000 * 1e18)

    with boa.env.prank(harvester_addr):
        crv_token.transfer(boa.env.generate_address(), crv_balance)
        cvx_token.transfer(boa.env.generate_address(), cvx_balance)

    with boa.env.prank(crvusd_minter):
        crvusd_token.mint(harvester_addr, expected_crvusd)

    # 6. Wait for more rewards and do second harvest
    boa.env.time_travel(seconds=86400 * 7)

    initial_user_crvusd = crvusd_token.balanceOf(user)
    initial_vault_assets = vault_contract.totalAssets()

    with boa.env.prank(harvest_manager):
        vault_contract.harvest(
            user,  # caller
            0,  # min_amount_out
            [],  # extra_rewards (empty - just CRV+CVX)
            b"",  # reward_hook_calldata (not used)
            target_hook_calldata,
            abi_encode("(uint256[])", [buy_amounts]),  # harvester_calldata
        )

    # 7. Check that second harvest results
    final_user_crvusd = crvusd_token.balanceOf(user)
    final_vault_assets = vault_contract.totalAssets()

    # Caller should receive fee in crvUSD
    assert (
        final_user_crvusd > initial_user_crvusd
    ), "Caller should receive crvUSD fee"

    # Vault assets should increase (from autocompounding)
    assert (
        final_vault_assets > initial_vault_assets
    ), "Vault assets should increase from compounding"

    # 8. Check that new orders were created with updated amounts
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
    pool_address: str, token_address: str
) -> bytes:

    target_sig = "add_liquidity(address,address,uint256,uint256)"
    target_selector = function_signature_to_4byte_selector(target_sig)
    target_encoded_args = abi_encode(
        "(address,address,uint256,uint256)",
        [pool_address, token_address, CRVUSD_INDEX_PYUSD_POOL, 0],
    )
    return target_selector + target_encoded_args


def test_cow_order_cancellation(test_cow_vault, crv_token, harvest_manager):
    vault_addr, strategy_addr, harvester_addr = test_cow_vault

    vault_contract = strategy.at(vault_addr)
    harvester_contract = cow_harvester.at(harvester_addr)

    buy_amounts = [int(100 * 1e18), int(50 * 1e18)]  # Non-zero amounts

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


def test_cow_order_expiry(test_cow_vault, crv_token, harvest_manager):
    vault_addr, strategy_addr, harvester_addr = test_cow_vault
    harvester_contract = cow_harvester.at(harvester_addr)

    # Create an order
    buy_amounts = [0, 0]

    with boa.env.prank(CURVE_TRICRV_POOL):
        crv_token.transfer(harvester_addr, int(1000 * 1e18))

    with boa.env.prank(harvest_manager):
        vault_contract = raac_vault.at(vault_addr)
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
