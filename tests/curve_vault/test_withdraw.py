import boa

from src import raac_vault, strategy


def test_vault_partial_withdraw_single_user(
    test_permissioned_vault,
    funded_accounts,
    pyusd_pool,
    get_base_reward_pool,
):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault
    user = funded_accounts[0]

    vault_contract = raac_vault.at(vault_addr)
    strategy_contract = strategy.at(strategy_addr)
    reward_pool = get_base_reward_pool(strategy_contract.rewards_contract())

    user_lp_balance = pyusd_pool.balanceOf(user)
    deposit_amount = user_lp_balance // 2

    with boa.env.prank(user):
        pyusd_pool.approve(vault_addr, deposit_amount)
        shares_received = vault_contract.deposit(deposit_amount, user)

    withdraw_assets = vault_contract.convertToAssets(shares_received // 2)

    initial_strategy_balance = reward_pool.balanceOf(strategy_addr)
    initial_user_lp_balance = pyusd_pool.balanceOf(user)
    initial_user_shares = vault_contract.balanceOf(user)

    with boa.env.prank(user):
        shares_burned = vault_contract.withdraw(withdraw_assets, user, user)
        logs = vault_contract.get_logs()
        withdraw_log = logs[-1]
        assert withdraw_log.sender == user
        assert withdraw_log.receiver == user
        assert withdraw_log.owner == user
        assert withdraw_log.assets == withdraw_assets
        assert withdraw_log.shares == shares_burned

    final_strategy_balance = reward_pool.balanceOf(strategy_addr)
    final_user_lp_balance = pyusd_pool.balanceOf(user)
    final_user_shares = vault_contract.balanceOf(user)

    assert final_strategy_balance == initial_strategy_balance - withdraw_assets
    assert final_user_lp_balance == initial_user_lp_balance + withdraw_assets
    assert final_user_shares == initial_user_shares - shares_burned


def test_vault_full_withdraw_single_user(
    test_permissioned_vault,
    funded_accounts,
    pyusd_pool,
    get_base_reward_pool,
):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault
    user = funded_accounts[1]

    vault_contract = raac_vault.at(vault_addr)
    strategy_contract = strategy.at(strategy_addr)
    reward_pool = get_base_reward_pool(strategy_contract.rewards_contract())

    user_lp_balance = pyusd_pool.balanceOf(user)

    with boa.env.prank(user):
        pyusd_pool.approve(vault_addr, user_lp_balance)
        shares_received = vault_contract.deposit(user_lp_balance, user)

    withdraw_assets = vault_contract.convertToAssets(shares_received)
    initial_strategy_balance = reward_pool.balanceOf(strategy_addr)

    with boa.env.prank(user):
        vault_contract.withdraw(withdraw_assets, user, user)

    final_strategy_balance = reward_pool.balanceOf(strategy_addr)
    final_user_lp_balance = pyusd_pool.balanceOf(user)
    final_user_shares = vault_contract.balanceOf(user)

    assert final_strategy_balance == initial_strategy_balance - withdraw_assets
    assert final_user_lp_balance == user_lp_balance
    assert final_user_shares == 0


def test_vault_withdraw_for_another_user(
    test_permissioned_vault,
    funded_accounts,
    pyusd_pool,
    get_base_reward_pool,
):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault
    owner = funded_accounts[2]
    receiver = funded_accounts[3]

    vault_contract = raac_vault.at(vault_addr)

    owner_lp_balance = pyusd_pool.balanceOf(owner)
    deposit_amount = owner_lp_balance // 2

    with boa.env.prank(owner):
        pyusd_pool.approve(vault_addr, deposit_amount)
        shares_received = vault_contract.deposit(deposit_amount, owner)

    withdraw_assets = vault_contract.convertToAssets(shares_received // 2)
    initial_receiver_lp_balance = pyusd_pool.balanceOf(receiver)
    initial_owner_shares = vault_contract.balanceOf(owner)

    with boa.env.prank(owner):
        shares_burned = vault_contract.withdraw(
            withdraw_assets, receiver, owner
        )
        logs = vault_contract.get_logs()
        withdraw_log = logs[-1]
        assert withdraw_log.sender == owner
        assert withdraw_log.receiver == receiver
        assert withdraw_log.owner == owner
        assert withdraw_log.assets == withdraw_assets
        assert withdraw_log.shares == shares_burned

    final_receiver_lp_balance = pyusd_pool.balanceOf(receiver)
    final_owner_shares = vault_contract.balanceOf(owner)

    assert (
        final_receiver_lp_balance
        == initial_receiver_lp_balance + withdraw_assets
    )
    assert final_owner_shares == initial_owner_shares - shares_burned


def test_vault_withdraw_more_than_balance_reverts(
    test_permissioned_vault, funded_accounts, pyusd_pool
):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault
    user = funded_accounts[4]

    vault_contract = raac_vault.at(vault_addr)

    user_lp_balance = pyusd_pool.balanceOf(user)
    deposit_amount = user_lp_balance // 2

    with boa.env.prank(user):
        pyusd_pool.approve(vault_addr, deposit_amount)
        shares_received = vault_contract.deposit(deposit_amount, user)

    max_withdrawable = vault_contract.convertToAssets(shares_received)

    with boa.env.prank(user):
        with boa.reverts():
            vault_contract.withdraw(max_withdrawable + 1, user, user)
