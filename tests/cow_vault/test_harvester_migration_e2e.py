import boa
from boa.util.abi import abi_encode

from src import raac_vault, strategy
from src.harvesters import cow_harvester
from tests.cow_vault.test_harvest_flow import _prepare_target_hook_calldata
from tests.utils.constants import CRV_TOKEN, CVX_TOKEN


def test_cow_harvester_migration_e2e(
    pyusd_cow_vault,
    pyusd_pool,
    vault_factory,
    crvusd_token,
    crvusd_minter,
    crv_token,
    cvx_token,
    funded_accounts,
    strategy_manager,
    harvest_manager,
    treasury,
):
    vault_addr, strategy_addr, old_harvester_addr = pyusd_cow_vault
    user = funded_accounts[0]

    vault_contract = raac_vault.at(vault_addr)
    old_harvester_contract = cow_harvester.at(old_harvester_addr)

    # User deposits into vault
    user_lp_balance = pyusd_pool.balanceOf(user)
    deposit_amount = user_lp_balance // 2

    with boa.env.prank(user):
        pyusd_pool.approve(vault_addr, deposit_amount)
        vault_contract.deposit(deposit_amount, user)

    initial_total_assets = vault_contract.totalAssets()
    initial_treasury_crvusd = crvusd_token.balanceOf(treasury)

    print(f"Initial vault total assets: {initial_total_assets / 1e18:.6f}")
    print(f"Initial treasury crvUSD: {initial_treasury_crvusd / 1e18:.6f}")

    boa.env.time_travel(seconds=86400 * 2)

    # First harvest - creates orders but no immediate rewards
    target_hook_calldata = _prepare_target_hook_calldata(
        pyusd_pool.address, crvusd_token.address, "pyusd"
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

    # Check that orders were created
    crv_order_exists, crv_order_info = old_harvester_contract.get_order_info(
        crv_token.address
    )
    cvx_order_exists, cvx_order_info = old_harvester_contract.get_order_info(
        cvx_token.address
    )

    assert crv_order_exists, "CRV order should be created"
    assert cvx_order_exists, "CVX order should be created"
    assert crv_order_info.sell_amount > 0, "CRV order should have sell amount"
    assert cvx_order_info.sell_amount > 0, "CVX order should have sell amount"

    print("First harvest completed - orders created")

    # Simulate CoW searcher execution - remove CRV/CVX and add crvUSD to old harvester
    crv_balance = crv_token.balanceOf(old_harvester_addr)
    cvx_balance = cvx_token.balanceOf(old_harvester_addr)

    expected_crvusd = int(10_000 * 1e18)

    with boa.env.prank(old_harvester_addr):
        crv_token.transfer(boa.env.generate_address(), crv_balance)
        cvx_token.transfer(boa.env.generate_address(), cvx_balance)

    with boa.env.prank(crvusd_minter):
        crvusd_token.mint(old_harvester_addr, expected_crvusd)

    print(
        f"CoW simulation completed - {expected_crvusd / 1e18:.6f} crvUSD added to old harvester"
    )

    # Check tokens accumulated in old harvester before migration
    old_harvester_crvusd_before = crvusd_token.balanceOf(old_harvester_addr)
    print(
        f"crvUSD in old harvester before migration: {old_harvester_crvusd_before / 1e18:.6f}"
    )

    # MIGRATION STEP: Create new harvester and migrate
    new_harvester_addr = vault_factory.deploy_harvester_instance(1, vault_addr)

    print(f"Old CoW harvester: {old_harvester_addr}")
    print(f"New CoW harvester: {new_harvester_addr}")

    # Migrate harvester with token migration (crvUSD should be migrated)
    migration_tokens = [CRV_TOKEN, CVX_TOKEN, crvusd_token.address]
    with boa.env.prank(strategy_manager):
        vault_contract.update_harvester(new_harvester_addr, migration_tokens)

    assert strategy.at(strategy_addr).harvester() == new_harvester_addr
    print("Harvester migration completed")

    # Verify hooks were transferred from old to new harvester
    old_harvester_contract = cow_harvester.at(old_harvester_addr)
    new_harvester_contract = cow_harvester.at(new_harvester_addr)

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

    # Check tokens were migrated
    old_harvester_crvusd_after = crvusd_token.balanceOf(old_harvester_addr)
    new_harvester_crvusd_after = crvusd_token.balanceOf(new_harvester_addr)

    print(
        f"crvUSD in old harvester after migration: {old_harvester_crvusd_after / 1e18:.6f}"
    )
    print(
        f"crvUSD in new harvester after migration: {new_harvester_crvusd_after / 1e18:.6f}"
    )

    assert (
        old_harvester_crvusd_after == 0
    ), "Old harvester should have no crvUSD left"
    assert (
        new_harvester_crvusd_after == old_harvester_crvusd_before
    ), "New harvester should receive all crvUSD"

    # Wait for more rewards and do second harvest with new harvester
    boa.env.time_travel(seconds=86400 * 7)

    initial_user_crvusd = crvusd_token.balanceOf(user)
    initial_vault_assets = vault_contract.totalAssets()

    print(
        f"Before final harvest - Total assets: {initial_vault_assets / 1e18:.6f}"
    )

    with boa.env.prank(harvest_manager):
        vault_contract.harvest(
            user,  # caller
            0,  # min_amount_out
            [],  # extra_rewards (empty - just CRV+CVX)
            b"",  # reward_hook_calldata (not used)
            target_hook_calldata,
            abi_encode("(uint256[])", [buy_amounts]),  # harvester_calldata
        )

    # Check the final harvest results
    final_user_crvusd = crvusd_token.balanceOf(user)
    final_vault_assets = vault_contract.totalAssets()
    final_treasury_crvusd = crvusd_token.balanceOf(treasury)

    # Calculate actual amounts received
    actual_treasury_fees = final_treasury_crvusd - initial_treasury_crvusd
    actual_caller_fees = final_user_crvusd - initial_user_crvusd
    actual_vault_increase = final_vault_assets - initial_vault_assets

    print("Final results:")
    print(f"  Treasury fees: {actual_treasury_fees / 1e18:.6f} crvUSD")
    print(f"  Caller fees: {actual_caller_fees / 1e18:.6f} crvUSD")
    print(f"  Vault increase: {actual_vault_increase / 1e18:.6f} LP tokens")
    print(f"  Final total assets: {final_vault_assets / 1e18:.6f}")

    # Validate migration and harvest worked
    assert (
        final_vault_assets > initial_vault_assets
    ), "Vault assets should increase after harvest"
    assert actual_treasury_fees > 0, "Treasury should receive platform fees"
    assert actual_caller_fees > 0, "Caller should receive fees"

    print("CoW harvester migration E2E test completed successfully")
