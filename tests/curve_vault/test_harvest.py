import boa
import pytest
from boa.util.abi import abi_encode
from eth_utils import function_signature_to_4byte_selector

from src import raac_vault, strategy
from tests.conftest import PYUSD_POOL_NAME, USDC_POOL_NAME, USDT_POOL_NAME
from tests.utils.constants import CRVUSD_POOLS
from tests.utils.harvest_calculations import (
    approx,
    calc_expected_fees,
    calc_expected_lp_tokens,
    calc_gross_harvest_amount,
)


@pytest.mark.parametrize(
    "pool_name", [PYUSD_POOL_NAME, USDC_POOL_NAME, USDT_POOL_NAME]
)
def test_vault_harvest_single_staker(
    vault_list,
    crvusd_token,
    crvusd_minter,
    funded_accounts,
    pool_list,
    get_base_reward_pool,
    harvest_manager,
    treasury,
    pool_name,
):
    crvusd_pool = pool_list[pool_name]
    vault_addr, strategy_addr, harvester_addr = vault_list[pool_name]
    user = funded_accounts[0]

    vault_contract = raac_vault.at(vault_addr)
    strategy_contract = strategy.at(strategy_addr)
    get_base_reward_pool(strategy_contract.rewards_contract())

    user_lp_balance = crvusd_pool.balanceOf(user)
    deposit_amount = user_lp_balance // 2

    with boa.env.prank(user):
        crvusd_pool.approve(vault_addr, deposit_amount)
        vault_contract.deposit(deposit_amount, user)

    initial_total_assets = vault_contract.totalAssets()
    initial_treasury_crvusd = crvusd_token.balanceOf(treasury)

    boa.env.time_travel(seconds=86400 * 10)

    # Calculate expected harvest amounts before harvest
    gross_estimated_harvest = calc_gross_harvest_amount(
        strategy_addr, strategy_contract.rewards_contract()
    )
    platform_fee_bps = strategy_contract.platform_fee()
    caller_fee_bps = strategy_contract.caller_fee()

    expected_platform_fees, expected_caller_fees, expected_net_harvest = (
        calc_expected_fees(
            gross_estimated_harvest, platform_fee_bps, caller_fee_bps
        )
    )

    print(
        f"Expected gross harvest: {gross_estimated_harvest / 1e18:.6f} crvUSD"
    )
    print(
        f"Expected platform fees: {expected_platform_fees / 1e18:.6f} crvUSD"
    )
    print(f"Expected caller fees: {expected_caller_fees / 1e18:.6f} crvUSD")
    print(f"Expected net harvest: {expected_net_harvest / 1e18:.6f} crvUSD")

    sig = "add_liquidity(address,address,uint256,uint256)"
    selector = function_signature_to_4byte_selector(sig)
    encoded_args = abi_encode(
        "(address,address,uint256,uint256)",
        [
            crvusd_pool.address,
            crvusd_token.address,
            CRVUSD_POOLS[pool_name]["crvusd_index"],
            0,
        ],
    )
    target_hook_calldata = selector + encoded_args

    with boa.env.prank(harvest_manager):
        vault_contract.harvest(user, 0, [], b"", target_hook_calldata, b"")

    final_total_assets = vault_contract.totalAssets()
    final_treasury_crvusd = crvusd_token.balanceOf(treasury)

    # Calculate actual amounts
    actual_treasury_fees = final_treasury_crvusd - initial_treasury_crvusd
    actual_vault_increase = final_total_assets - initial_total_assets

    print(f"Actual treasury fees: {actual_treasury_fees / 1e18:.6f} crvUSD")
    print(
        f"Actual vault increase: {actual_vault_increase / 1e18:.6f} LP tokens"
    )
    print("-" * 50)

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

    # Verify precise fee distributions (allowing more tolerance for oracle-based swaps)
    assert approx(
        actual_treasury_fees, expected_platform_fees, 5e-2
    ), f"Treasury fees mismatch: got {actual_treasury_fees}, expected {expected_platform_fees}"

    assert approx(
        actual_vault_increase, expected_vault_increase_lp, 5e-2
    ), f"Vault increase mismatch: got {actual_vault_increase}, expected {expected_vault_increase_lp}"


@pytest.mark.parametrize(
    "pool_name", [PYUSD_POOL_NAME, USDC_POOL_NAME, USDT_POOL_NAME]
)
def test_vault_harvest_multiple_stakers(
    vault_list,
    crvusd_token,
    crvusd_minter,
    funded_accounts,
    pool_list,
    get_base_reward_pool,
    harvest_manager,
    treasury,
    pool_name,
):
    crvusd_pool = pool_list[pool_name]
    vault_addr, strategy_addr, harvester_addr = vault_list[pool_name]

    vault_contract = raac_vault.at(vault_addr)
    strategy_contract = strategy.at(strategy_addr)
    get_base_reward_pool(strategy_contract.rewards_contract())

    user_deposits = {}
    for i, user in enumerate(funded_accounts[:3]):
        user_lp_balance = crvusd_pool.balanceOf(user)
        deposit_amount = user_lp_balance // 3

        with boa.env.prank(user):
            crvusd_pool.approve(vault_addr, deposit_amount)
            shares_received = vault_contract.deposit(deposit_amount, user)
            user_deposits[user] = {
                "deposit": deposit_amount,
                "shares": shares_received,
            }

    initial_total_assets = vault_contract.totalAssets()
    initial_treasury_crvusd = crvusd_token.balanceOf(treasury)

    boa.env.time_travel(seconds=86400 * 7)

    # Calculate expected harvest amounts before harvest
    gross_estimated_harvest = calc_gross_harvest_amount(
        strategy_addr, strategy_contract.rewards_contract()
    )
    platform_fee_bps = strategy_contract.platform_fee()
    caller_fee_bps = strategy_contract.caller_fee()

    expected_platform_fees, expected_caller_fees, expected_net_harvest = (
        calc_expected_fees(
            gross_estimated_harvest, platform_fee_bps, caller_fee_bps
        )
    )

    print(
        f"Expected gross harvest: {gross_estimated_harvest / 1e18:.6f} crvUSD"
    )
    print(
        f"Expected platform fees: {expected_platform_fees / 1e18:.6f} crvUSD"
    )
    print(f"Expected net harvest: {expected_net_harvest / 1e18:.6f} crvUSD")

    sig = "add_liquidity(address,address,uint256,uint256)"
    selector = function_signature_to_4byte_selector(sig)
    encoded_args = abi_encode(
        "(address,address,uint256,uint256)",
        [
            crvusd_pool.address,
            crvusd_token.address,
            CRVUSD_POOLS[pool_name]["crvusd_index"],
            0,
        ],
    )
    target_hook_calldata = selector + encoded_args

    with boa.env.prank(harvest_manager):
        vault_contract.harvest(
            funded_accounts[0], 0, [], b"", target_hook_calldata, b""
        )

    final_total_assets = vault_contract.totalAssets()
    final_treasury_crvusd = crvusd_token.balanceOf(treasury)

    # Calculate actual amounts
    actual_treasury_fees = final_treasury_crvusd - initial_treasury_crvusd
    actual_vault_increase = final_total_assets - initial_total_assets

    print(f"Actual treasury fees: {actual_treasury_fees / 1e18:.6f} crvUSD")
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

    # Verify precise fee distributions
    assert approx(
        actual_treasury_fees, expected_platform_fees, 5e-2
    ), f"Treasury fees mismatch: got {actual_treasury_fees}, expected {expected_platform_fees}"

    assert approx(
        actual_vault_increase, expected_vault_increase_lp, 5e-2
    ), f"Vault increase mismatch: got {actual_vault_increase}, expected {expected_vault_increase_lp}"

    for user, data in user_deposits.items():
        user_asset_value = vault_contract.convertToAssets(data["shares"])
        assert user_asset_value >= data["deposit"]


@pytest.mark.parametrize(
    "pool_name", [PYUSD_POOL_NAME, USDC_POOL_NAME, USDT_POOL_NAME]
)
def test_vault_withdraw_after_harvest_profit(
    vault_list,
    crvusd_token,
    funded_accounts,
    pool_list,
    get_base_reward_pool,
    harvest_manager,
    treasury,
    pool_name,
):
    crvusd_pool = pool_list[pool_name]
    vault_addr, strategy_addr, harvester_addr = vault_list[pool_name]
    user = funded_accounts[0]

    vault_contract = raac_vault.at(vault_addr)

    user_lp_balance = crvusd_pool.balanceOf(user)
    deposit_amount = user_lp_balance // 2

    with boa.env.prank(user):
        crvusd_pool.approve(vault_addr, deposit_amount)
        shares_received = vault_contract.deposit(deposit_amount, user)

    initial_treasury_crvusd = crvusd_token.balanceOf(treasury)
    boa.env.time_travel(seconds=86400 * 7)

    sig = "add_liquidity(address,address,uint256,uint256)"
    selector = function_signature_to_4byte_selector(sig)
    encoded_args = abi_encode(
        "(address,address,uint256,uint256)",
        [
            crvusd_pool.address,
            crvusd_token.address,
            CRVUSD_POOLS[pool_name]["crvusd_index"],
            0,
        ],
    )
    target_hook_calldata = selector + encoded_args

    with boa.env.prank(harvest_manager):
        vault_contract.harvest(user, 0, [], b"", target_hook_calldata, b"")

    final_treasury_crvusd = crvusd_token.balanceOf(treasury)
    assert (
        final_treasury_crvusd > initial_treasury_crvusd
    ), "Treasury should receive crvUSD platform fees"

    initial_user_lp_balance = crvusd_pool.balanceOf(user)
    withdrawable_assets = vault_contract.convertToAssets(shares_received)

    with boa.env.prank(user):
        vault_contract.withdraw(withdrawable_assets, user, user)

    final_user_lp_balance = crvusd_pool.balanceOf(user)
    total_received = final_user_lp_balance - initial_user_lp_balance

    assert total_received > deposit_amount


@pytest.mark.parametrize(
    "pool_name", [PYUSD_POOL_NAME, USDC_POOL_NAME, USDT_POOL_NAME]
)
def test_vault_harvest_reverts_high_min_amount_out(
    vault_list,
    crvusd_token,
    funded_accounts,
    pool_list,
    harvest_manager,
    treasury,
    pool_name,
):
    crvusd_pool = pool_list[pool_name]
    vault_addr, strategy_addr, harvester_addr = vault_list[pool_name]
    user = funded_accounts[0]

    vault_contract = raac_vault.at(vault_addr)

    user_lp_balance = crvusd_pool.balanceOf(user)
    deposit_amount = user_lp_balance // 2

    with boa.env.prank(user):
        crvusd_pool.approve(vault_addr, deposit_amount)
        vault_contract.deposit(deposit_amount, user)

    boa.env.time_travel(seconds=86400 * 7)

    sig = "add_liquidity(address,address,uint256,uint256)"
    selector = function_signature_to_4byte_selector(sig)
    encoded_args = abi_encode(
        "(address,address,uint256,uint256)",
        [
            crvusd_pool.address,
            crvusd_token.address,
            CRVUSD_POOLS[pool_name]["crvusd_index"],
            2**256 - 1,
        ],
    )
    target_hook_calldata = selector + encoded_args

    with boa.env.prank(harvest_manager):
        with boa.reverts():
            vault_contract.harvest(
                user, 2**256 - 1, [], b"", target_hook_calldata, b""
            )


@pytest.mark.parametrize(
    "pool_name", [PYUSD_POOL_NAME, USDC_POOL_NAME, USDT_POOL_NAME]
)
def test_vault_streaming_withdrawals_different_times(
    vault_list,
    crvusd_token,
    crvusd_minter,
    funded_accounts,
    pool_list,
    get_base_reward_pool,
    harvest_manager,
    treasury,
    pool_name,
):
    crvusd_pool = pool_list[pool_name]
    vault_addr, strategy_addr, harvester_addr = vault_list[pool_name]
    user1, user2 = funded_accounts[0], funded_accounts[1]

    vault_contract = raac_vault.at(vault_addr)
    strategy_contract = strategy.at(strategy_addr)
    get_base_reward_pool(strategy_contract.rewards_contract())

    user1_lp_balance = crvusd_pool.balanceOf(user1)
    user2_lp_balance = crvusd_pool.balanceOf(user2)
    deposit_amount1 = user1_lp_balance // 2
    deposit_amount2 = user2_lp_balance // 2

    with boa.env.prank(user1):
        crvusd_pool.approve(vault_addr, deposit_amount1)
        shares1 = vault_contract.deposit(deposit_amount1, user1)

    with boa.env.prank(user2):
        crvusd_pool.approve(vault_addr, deposit_amount2)
        shares2 = vault_contract.deposit(deposit_amount2, user2)

    boa.env.time_travel(seconds=86400 * 7)

    gross_estimated_harvest = calc_gross_harvest_amount(
        strategy_addr, strategy_contract.rewards_contract()
    )
    platform_fee_bps = strategy_contract.platform_fee()
    caller_fee_bps = strategy_contract.caller_fee()

    expected_platform_fees, expected_caller_fees, expected_net_harvest = (
        calc_expected_fees(
            gross_estimated_harvest, platform_fee_bps, caller_fee_bps
        )
    )

    expected_vault_increase_lp = calc_expected_lp_tokens(
        crvusd_pool,
        harvester_addr,
        crvusd_token,
        crvusd_minter,
        expected_net_harvest,
        pool_name,
    )

    print("Setup:")
    print(f"User1 shares: {shares1 / 1e18:.2f}")
    print(f"User2 shares: {shares2 / 1e18:.2f}")
    print(f"Expected net harvest: {expected_net_harvest / 1e18:.6f} crvUSD")
    print(
        f"Expected vault increase: {expected_vault_increase_lp / 1e18:.6f} LP tokens"
    )

    sig = "add_liquidity(address,address,uint256,uint256)"
    selector = function_signature_to_4byte_selector(sig)
    encoded_args = abi_encode(
        "(address,address,uint256,uint256)",
        [
            crvusd_pool.address,
            crvusd_token.address,
            CRVUSD_POOLS[pool_name]["crvusd_index"],
            0,
        ],
    )
    target_hook_calldata = selector + encoded_args

    with boa.env.prank(harvest_manager):
        vault_contract.harvest(user1, 0, [], b"", target_hook_calldata, b"")

    streaming_period = vault_contract.profit_max_unlock_time()
    print(
        f"Streaming period: {streaming_period} seconds ({streaming_period // 86400} days)"
    )

    boa.env.time_travel(seconds=86400)

    user1_max_withdraw_1day = vault_contract.maxWithdraw(user1)
    expected_1day = (
        shares1 * vault_contract.totalAssets() // vault_contract.totalSupply()
    )

    print("\nAfter 1 day of streaming:")
    print(f"User1 expected withdraw: {expected_1day / 1e18:.6f} LP")
    print(
        f"User1 actual max withdraw: {user1_max_withdraw_1day / 1e18:.6f} LP"
    )
    print(f"Unlocked shares: {vault_contract.unlocked_shares() / 1e18:.2f}")
    print(
        f"Locked shares: {vault_contract.balanceOf(vault_contract.address) / 1e18:.2f}"
    )

    initial_user1_lp = crvusd_pool.balanceOf(user1)
    with boa.env.prank(user1):
        vault_contract.withdraw(user1_max_withdraw_1day, user1, user1)
    final_user1_lp = crvusd_pool.balanceOf(user1)
    user1_withdrawn = final_user1_lp - initial_user1_lp

    print(f"User1 actually withdrew: {user1_withdrawn / 1e18:.6f} LP")

    boa.env.time_travel(seconds=streaming_period - 86400)

    user2_max_withdraw_end = vault_contract.maxWithdraw(user2)
    expected_end = (
        shares2 * vault_contract.totalAssets() // vault_contract.totalSupply()
    )

    print("\nAt end of streaming period:")
    print(f"User2 expected withdraw: {expected_end / 1e18:.6f} LP")
    print(f"User2 actual max withdraw: {user2_max_withdraw_end / 1e18:.6f} LP")
    print(f"Unlocked shares: {vault_contract.unlocked_shares() / 1e18:.2f}")
    print(
        f"Locked shares: {vault_contract.balanceOf(vault_contract.address) / 1e18:.2f}"
    )

    initial_user2_lp = crvusd_pool.balanceOf(user2)
    with boa.env.prank(user2):
        vault_contract.withdraw(user2_max_withdraw_end, user2, user2)
    final_user2_lp = crvusd_pool.balanceOf(user2)
    user2_withdrawn = final_user2_lp - initial_user2_lp

    print(f"User2 actually withdrew: {user2_withdrawn / 1e18:.6f} LP")

    total_withdrawn = user1_withdrawn + user2_withdrawn
    total_deposited = deposit_amount1 + deposit_amount2

    print("\nSummary:")
    print(f"Total deposited: {total_deposited / 1e18:.6f} LP")
    print(f"Total withdrawn: {total_withdrawn / 1e18:.6f} LP")
    print(f"Net gain: {(total_withdrawn - total_deposited) / 1e18:.6f} LP")

    assert user1_max_withdraw_1day == pytest.approx(expected_1day, rel=1e-6)
    assert user2_max_withdraw_end == pytest.approx(expected_end, rel=1e-6)
    assert user1_withdrawn == pytest.approx(user1_max_withdraw_1day, rel=1e-6)
    assert user2_withdrawn == pytest.approx(user2_max_withdraw_end, rel=1e-6)


@pytest.mark.parametrize(
    "pool_name", [PYUSD_POOL_NAME, USDC_POOL_NAME, USDT_POOL_NAME]
)
def test_harvest_zero_supply_reverts(
    vault_list,
    harvest_manager,
    pool_name,
):
    vault_addr, strategy_addr, harvester_addr = vault_list[pool_name]
    vault_contract = raac_vault.at(vault_addr)

    # Vault should have zero supply initially
    assert vault_contract.totalSupply() == 0

    # Attempt to harvest with zero supply should revert
    with boa.reverts("No supply"):
        with boa.env.prank(harvest_manager):
            vault_contract.harvest(harvest_manager, 0, [], b"", b"", b"")
