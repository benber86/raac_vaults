import boa
import pytest
from boa.util.abi import abi_encode
from eth_utils import function_signature_to_4byte_selector

from src import raac_vault, strategy
from tests.conftest import PYUSD_POOL_NAME, USDC_POOL_NAME
from tests.utils.constants import CRVUSD_POOLS


@pytest.mark.parametrize("pool_name", [PYUSD_POOL_NAME, USDC_POOL_NAME])
def test_vault_harvest_single_staker(
    vault_list,
    crvusd_token,
    funded_accounts,
    pool_list,
    get_base_reward_pool,
    harvest_manager,
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

    final_total_assets = vault_contract.totalAssets()
    assert final_total_assets > initial_total_assets


@pytest.mark.parametrize("pool_name", [PYUSD_POOL_NAME, USDC_POOL_NAME])
def test_vault_harvest_multiple_stakers(
    vault_list,
    crvusd_token,
    funded_accounts,
    pool_list,
    get_base_reward_pool,
    harvest_manager,
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
        vault_contract.harvest(
            funded_accounts[0], 0, [], b"", target_hook_calldata, b""
        )

    final_total_assets = vault_contract.totalAssets()
    assert final_total_assets > initial_total_assets

    for user, data in user_deposits.items():
        user_asset_value = vault_contract.convertToAssets(data["shares"])
        assert user_asset_value >= data["deposit"]


@pytest.mark.parametrize("pool_name", [PYUSD_POOL_NAME, USDC_POOL_NAME])
def test_vault_withdraw_after_harvest_profit(
    vault_list,
    crvusd_token,
    funded_accounts,
    pool_list,
    get_base_reward_pool,
    harvest_manager,
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

    initial_user_lp_balance = crvusd_pool.balanceOf(user)
    withdrawable_assets = vault_contract.convertToAssets(shares_received)

    with boa.env.prank(user):
        vault_contract.withdraw(withdrawable_assets, user, user)

    final_user_lp_balance = crvusd_pool.balanceOf(user)
    total_received = final_user_lp_balance - initial_user_lp_balance

    assert total_received > deposit_amount


@pytest.mark.parametrize("pool_name", [PYUSD_POOL_NAME, USDC_POOL_NAME])
def test_vault_harvest_reverts_high_min_amount_out(
    vault_list,
    crvusd_token,
    funded_accounts,
    pool_list,
    harvest_manager,
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
