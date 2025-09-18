import boa
import pytest
from boa.contracts.abi.abi_contract import ABIContractFactory
from boa.util.abi import abi_encode
from eth_utils import function_signature_to_4byte_selector

from src import raac_vault, strategy
from src.harvesters import curve_harvester
from tests.utils.abis import ERC20_ABI
from tests.utils.constants import CRV_TOKEN, CRVUSD_POOLS, CVX_TOKEN
from tests.utils.harvest_calculations import (
    calc_expected_fees,
    calc_gross_harvest_amount,
)


def test_curve_harvester_migration_e2e(
    pyusd_vault,
    pyusd_pool,
    vault_factory,
    crvusd_token,
    funded_accounts,
    strategy_manager,
    harvest_manager,
    treasury,
    get_base_reward_pool,
):
    vault_addr, strategy_addr, old_harvester_addr = pyusd_vault
    user = funded_accounts[0]

    vault_contract = raac_vault.at(vault_addr)
    strategy_contract = strategy.at(strategy_addr)
    get_base_reward_pool(strategy_contract.rewards_contract())

    user_lp_balance = pyusd_pool.balanceOf(user)
    deposit_amount = user_lp_balance // 2

    with boa.env.prank(user):
        pyusd_pool.approve(vault_addr, deposit_amount)
        vault_contract.deposit(deposit_amount, user)

    initial_total_assets = vault_contract.totalAssets()
    initial_treasury_crvusd = crvusd_token.balanceOf(treasury)

    print(f"Initial vault total assets: {initial_total_assets / 1e18:.6f}")
    print(f"Initial treasury crvUSD: {initial_treasury_crvusd / 1e18:.6f}")

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

    # MIGRATION STEP: Create new harvester and migrate
    new_harvester_addr = vault_factory.deploy_harvester_instance(0, vault_addr)

    print(f"Old Curve harvester: {old_harvester_addr}")
    print(f"New Curve harvester: {new_harvester_addr}")

    # Migrate harvester (empty token array for Curve)
    with boa.env.prank(strategy_manager):
        vault_contract.update_harvester(new_harvester_addr, [])

    assert strategy_contract.harvester() == new_harvester_addr
    print("Harvester migration completed")

    # Verify hooks were transferred from old to new harvester
    old_harvester_contract = curve_harvester.at(old_harvester_addr)
    new_harvester_contract = curve_harvester.at(new_harvester_addr)

    old_target_hook = old_harvester_contract.target_hook()
    old_extra_reward_hook = old_harvester_contract.extra_reward_hook()
    new_target_hook = new_harvester_contract.target_hook()
    new_extra_reward_hook = new_harvester_contract.extra_reward_hook()

    print("Hook migration:")
    print(f"  Old harvester target hook: {old_target_hook}")
    print(f"  New harvester target hook: {new_target_hook}")
    print(f"  Old harvester extra reward hook: {old_extra_reward_hook}")
    print(f"  New harvester extra reward hook: {new_extra_reward_hook}")

    assert (
        new_target_hook == old_target_hook
    ), "Target hook should be transferred to new harvester"
    assert (
        new_extra_reward_hook == old_extra_reward_hook
    ), "Extra reward hook should be transferred to new harvester"

    # Prepare target hook calldata for adding liquidity
    sig = "add_liquidity(address,address,uint256,uint256)"
    selector = function_signature_to_4byte_selector(sig)
    encoded_args = abi_encode(
        "(address,address,uint256,uint256)",
        [
            pyusd_pool.address,
            crvusd_token.address,
            CRVUSD_POOLS["pyusd"]["crvusd_index"],
            0,
        ],
    )
    target_hook_calldata = selector + encoded_args

    # Execute harvest with new harvester
    with boa.env.prank(harvest_manager):
        vault_contract.harvest(user, 0, [], b"", target_hook_calldata, b"")

    final_total_assets = vault_contract.totalAssets()
    final_treasury_crvusd = crvusd_token.balanceOf(treasury)

    # Calculate actual amounts
    actual_treasury_fees = final_treasury_crvusd - initial_treasury_crvusd
    actual_vault_increase = final_total_assets - initial_total_assets

    print("Final results:")
    print(f"  Treasury fees: {actual_treasury_fees / 1e18:.6f} crvUSD")
    print(f"  Vault increase: {actual_vault_increase / 1e18:.6f} LP tokens")
    print(f"  Final total assets: {final_total_assets / 1e18:.6f}")

    # Validate migration and harvest worked
    assert (
        final_total_assets > initial_total_assets
    ), "Total assets should increase after harvest"
    assert actual_treasury_fees > 0, "Treasury should receive platform fees"

    # Validate that new harvester has minimal leftover tokens
    cvx_token = ABIContractFactory("ERC20", ERC20_ABI).at(CVX_TOKEN)
    crv_token = ABIContractFactory("ERC20", ERC20_ABI).at(CRV_TOKEN)

    new_harvester_cvx = cvx_token.balanceOf(new_harvester_addr)
    new_harvester_crv = crv_token.balanceOf(new_harvester_addr)
    old_harvester_cvx = cvx_token.balanceOf(old_harvester_addr)
    old_harvester_crv = crv_token.balanceOf(old_harvester_addr)

    print("Token balances after harvest:")
    print(f"  New harvester CVX: {new_harvester_cvx / 1e18:.6f}")
    print(f"  New harvester CRV: {new_harvester_crv / 1e18:.6f}")
    print(f"  Old harvester CVX: {old_harvester_cvx / 1e18:.6f}")
    print(f"  Old harvester CRV: {old_harvester_crv / 1e18:.6f}")

    # Both harvesters should have minimal dust (Curve processes immediately)
    assert new_harvester_cvx == pytest.approx(
        0, rel=1e-4
    ), "New harvester should have minimal CVX left"
    assert new_harvester_crv == pytest.approx(
        0, rel=1e-4
    ), "New harvester should have minimal CRV left"
    assert old_harvester_cvx == pytest.approx(
        0, rel=1e-4
    ), "Old harvester should have minimal CVX left"
    assert old_harvester_crv == pytest.approx(
        0, rel=1e-4
    ), "Old harvester should have minimal CRV left"

    print("Curve harvester migration E2E test completed successfully")
