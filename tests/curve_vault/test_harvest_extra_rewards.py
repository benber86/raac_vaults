import boa
import pytest
from boa.util.abi import abi_encode
from eth_utils import function_signature_to_4byte_selector

from src import raac_vault
from tests.conftest import PYUSD_POOL_NAME, USDC_POOL_NAME, ZERO_ADDRESS
from tests.utils.constants import (
    CRVUSD_POOLS,
    CRVUSD_TOKEN,
    CURVE_TRICRV_POOL,
    RSUP_TOKEN,
    RSUP_WETH_POOL,
    WETH_TOKEN,
)


@pytest.mark.parametrize("pool_name", [PYUSD_POOL_NAME, USDC_POOL_NAME])
def test_vault_harvest_single_staker_with_extra_rewards(
    extra_rewards_vault_list,
    crvusd_token,
    funded_accounts,
    pool_list,
    get_base_reward_pool,
    set_up_extra_rewards_for_pool,
    treasury,
    harvest_manager,
    pool_name,
):
    crvusd_pool = pool_list[pool_name]
    vault_addr, strategy_addr, harvester_addr = extra_rewards_vault_list[
        pool_name
    ]
    user = funded_accounts[0]

    vault_contract = raac_vault.at(vault_addr)

    user_lp_balance = crvusd_pool.balanceOf(user)
    deposit_amount = user_lp_balance // 2

    with boa.env.prank(user):
        crvusd_pool.approve(vault_addr, deposit_amount)
        vault_contract.deposit(deposit_amount, user)

    # Set up extra rewards
    set_up_extra_rewards_for_pool()

    initial_total_assets = vault_contract.totalAssets()

    initial_treasury_crvusd = crvusd_token.balanceOf(treasury)

    boa.env.time_travel(seconds=86400 * 7)

    # Target hook calldata for adding liquidity
    target_sig = "add_liquidity(address,address,uint256,uint256)"
    target_selector = function_signature_to_4byte_selector(target_sig)
    target_encoded_args = abi_encode(
        "(address,address,uint256,uint256)",
        [
            crvusd_pool.address,
            crvusd_token.address,
            CRVUSD_POOLS[pool_name]["crvusd_index"],
            0,
        ],
    )
    target_hook_calldata = target_selector + target_encoded_args

    # Extra reward hook calldata for RSUP -> WETH -> crvUSD using NEW ROUTER FORMAT
    # Route: [RSUP, RSUP/WETH pool, WETH, TRICRV pool, crvUSD, 0x00, ...]
    route = [
        RSUP_TOKEN,  # Initial token
        RSUP_WETH_POOL,  # RSUP/WETH pool
        WETH_TOKEN,  # Intermediate token
        CURVE_TRICRV_POOL,  # TRICRV pool
        CRVUSD_TOKEN,  # Final token
        ZERO_ADDRESS,  # End marker
        ZERO_ADDRESS,  # Padding
        ZERO_ADDRESS,  # Padding
        ZERO_ADDRESS,  # Padding
        ZERO_ADDRESS,  # Padding
        ZERO_ADDRESS,  # Padding (11 total)
    ]

    # swap params format: [i, j, swap_type, pool_type, n_coins] for each swap
    swap_params = [
        [
            1,
            0,
            1,
            20,
            2,
        ],  # RSUP (index 1) -> WETH (index 0), exchange, twocrypto-ng, 2 coins
        [
            1,
            0,
            1,
            30,
            3,
        ],  # WETH (index 1) -> crvUSD (index 0), exchange, tricrypto-ng, 3 coins
        [0, 0, 0, 0, 0],  # Unused
        [0, 0, 0, 0, 0],  # Unused
        [0, 0, 0, 0, 0],  # Unused
    ]

    pools = [
        RSUP_WETH_POOL,  # First pool (from UI output)
        CURVE_TRICRV_POOL,  # Second pool (from UI output)
        ZERO_ADDRESS,  # Unused
        ZERO_ADDRESS,  # Unused
        ZERO_ADDRESS,  # Unused
    ]

    # Update function signature for new router
    reward_sig = (
        "process_extra_rewards(address,address[11],uint256[5][5],address[5])"
    )
    reward_selector = function_signature_to_4byte_selector(reward_sig)
    reward_encoded_args = abi_encode(
        "(address,address[11],uint256[5][5],address[5])",
        [RSUP_TOKEN, route, swap_params, pools],
    )
    reward_hook_calldata = reward_selector + reward_encoded_args

    extra_rewards = [RSUP_TOKEN]

    boa.env.time_travel(seconds=86400 * 7)

    with boa.env.prank(harvest_manager):
        vault_contract.harvest(
            user,
            0,
            extra_rewards,
            reward_hook_calldata,
            target_hook_calldata,
            b"",
        )

    final_total_assets = vault_contract.totalAssets()
    final_treasury_crvusd = crvusd_token.balanceOf(treasury)

    assert (
        final_total_assets > initial_total_assets
    ), "Vault assets should increase after harvest"

    treasury_crvusd_received = final_treasury_crvusd - initial_treasury_crvusd
    assert (
        treasury_crvusd_received > 0
    ), "Treasury should receive crvUSD platform fees"

    print(f"Treasury crvUSD received: {treasury_crvusd_received / 1e18:.6f}")
    print(
        f"Vault assets increase: {(final_total_assets - initial_total_assets) / 1e18:.6f}"
    )
