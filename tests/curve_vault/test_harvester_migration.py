import boa
import pytest
from boa.contracts.abi.abi_contract import ABIContractFactory

from src import raac_vault, strategy
from src.harvesters import curve_harvester
from tests.utils.abis import ERC20_ABI
from tests.utils.constants import CRV_TOKEN, CVX_TOKEN, RSUP_TOKEN


def test_curve_harvester_migration_empty_tokens(
    pyusd_vault,
    vault_factory,
    funded_accounts,
    strategy_manager,
):
    vault_addr, strategy_addr, old_harvester_addr = pyusd_vault

    vault_contract = raac_vault.at(vault_addr)
    strategy_contract = strategy.at(strategy_addr)
    new_harvester_addr = curve_harvester.deploy(vault_factory.address)
    new_harvester_addr.set_strategy(strategy_addr)

    with boa.env.prank(strategy_manager):
        vault_contract.update_harvester(new_harvester_addr.address, [])

    assert strategy_contract.harvester() == new_harvester_addr.address

    # Verify hooks were transferred from old to new harvester
    old_harvester_contract = curve_harvester.at(old_harvester_addr)

    old_target_hook = old_harvester_contract.target_hook()
    old_extra_reward_hook = old_harvester_contract.extra_reward_hook()
    new_target_hook = new_harvester_addr.target_hook()
    new_extra_reward_hook = new_harvester_addr.extra_reward_hook()

    print("Migration completed for pyusd pool with empty token array")
    print(f"Old harvester: {old_harvester_addr}")
    print(f"New harvester: {new_harvester_addr.address}")
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


def test_curve_harvester_migration_with_extra_rewards(
    pyusd_vault,
    vault_factory,
    funded_accounts,
    strategy_manager,
    set_up_extra_rewards_for_pool,
):
    vault_addr, strategy_addr, old_harvester_addr = pyusd_vault

    vault_contract = raac_vault.at(vault_addr)
    strategy_contract = strategy.at(strategy_addr)

    set_up_extra_rewards_for_pool()

    rsup_token = ABIContractFactory("ERC20", ERC20_ABI).at(RSUP_TOKEN)
    cvx_token = ABIContractFactory("ERC20", ERC20_ABI).at(CVX_TOKEN)
    crv_token = ABIContractFactory("ERC20", ERC20_ABI).at(CRV_TOKEN)

    boa.deal(rsup_token, old_harvester_addr, 1000 * 10**18)

    initial_rsup_balance = rsup_token.balanceOf(old_harvester_addr)
    initial_cvx_balance = cvx_token.balanceOf(old_harvester_addr)
    initial_crv_balance = crv_token.balanceOf(old_harvester_addr)

    print(f"Initial balances in old harvester {old_harvester_addr}:")
    print(f"  RSUP: {initial_rsup_balance / 1e18:.6f}")
    print(f"  CVX: {initial_cvx_balance / 1e18:.6f}")
    print(f"  CRV: {initial_crv_balance / 1e18:.6f}")

    new_harvester_addr = curve_harvester.deploy(vault_factory.address)
    new_harvester_addr.set_strategy(strategy_addr)

    migration_tokens = [RSUP_TOKEN, CVX_TOKEN, CRV_TOKEN]

    with boa.env.prank(strategy_manager):
        vault_contract.update_harvester(
            new_harvester_addr.address, migration_tokens
        )

    assert strategy_contract.harvester() == new_harvester_addr.address

    # Verify hooks were transferred from old to new harvester
    old_harvester_contract = curve_harvester.at(old_harvester_addr)

    old_target_hook = old_harvester_contract.target_hook()
    old_extra_reward_hook = old_harvester_contract.extra_reward_hook()
    new_target_hook = new_harvester_addr.target_hook()
    new_extra_reward_hook = new_harvester_addr.extra_reward_hook()

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

    final_old_rsup_balance = rsup_token.balanceOf(old_harvester_addr)
    final_old_cvx_balance = cvx_token.balanceOf(old_harvester_addr)
    final_old_crv_balance = crv_token.balanceOf(old_harvester_addr)

    final_new_rsup_balance = rsup_token.balanceOf(new_harvester_addr.address)
    final_new_cvx_balance = cvx_token.balanceOf(new_harvester_addr.address)
    final_new_crv_balance = crv_token.balanceOf(new_harvester_addr.address)

    print(f"Final balances in old harvester {old_harvester_addr}:")
    print(f"  RSUP: {final_old_rsup_balance / 1e18:.6f}")
    print(f"  CVX: {final_old_cvx_balance / 1e18:.6f}")
    print(f"  CRV: {final_old_crv_balance / 1e18:.6f}")

    print(f"Final balances in new harvester {new_harvester_addr.address}:")
    print(f"  RSUP: {final_new_rsup_balance / 1e18:.6f}")
    print(f"  CVX: {final_new_cvx_balance / 1e18:.6f}")
    print(f"  CRV: {final_new_crv_balance / 1e18:.6f}")

    assert final_old_rsup_balance == pytest.approx(
        0, rel=1e-4
    ), "Old harvester should have no RSUP tokens left"
    assert final_old_cvx_balance == pytest.approx(
        0, rel=1e-4
    ), "Old harvester should have no CVX tokens left"
    assert final_old_crv_balance == pytest.approx(
        0, rel=1e-4
    ), "Old harvester should have no CRV tokens left"

    assert final_new_rsup_balance == pytest.approx(
        initial_rsup_balance, rel=1e-4
    ), "New harvester should receive all RSUP tokens"
