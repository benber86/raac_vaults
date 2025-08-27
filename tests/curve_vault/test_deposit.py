import boa

from src import raac_vault, strategy


def test_vault_partial_deposit_single_user(
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

    initial_strategy_balance = reward_pool.balanceOf(strategy_addr)
    initial_vault_shares = vault_contract.balanceOf(user)

    with boa.env.prank(user):
        pyusd_pool.approve(vault_addr, deposit_amount)
        shares = vault_contract.deposit(deposit_amount, user)
        logs = vault_contract.get_logs()
        deposit_log = logs[-1]
        assert deposit_log.sender == user
        assert deposit_log.owner == user
        assert deposit_log.assets == deposit_amount
        assert deposit_log.shares == shares

    final_strategy_balance = reward_pool.balanceOf(strategy_addr)
    final_vault_shares = vault_contract.balanceOf(user)

    assert final_strategy_balance == initial_strategy_balance + deposit_amount
    assert final_vault_shares == initial_vault_shares + shares


def test_vault_deposit_multiple_users(
    test_permissioned_vault,
    funded_accounts,
    pyusd_pool,
    get_base_reward_pool,
):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    vault_contract = raac_vault.at(vault_addr)
    strategy_contract = strategy.at(strategy_addr)

    reward_pool = get_base_reward_pool(strategy_contract.rewards_contract())

    initial_strategy_balance = reward_pool.balanceOf(strategy_addr)

    total_deposited = 0
    user_shares = {}

    for i, user in enumerate(funded_accounts[:3]):
        user_lp_balance = pyusd_pool.balanceOf(user)
        deposit_amount = user_lp_balance // 3

        with boa.env.prank(user):
            pyusd_pool.approve(vault_addr, deposit_amount)
            shares = vault_contract.deposit(deposit_amount, user)
            user_shares[user] = shares
            total_deposited += deposit_amount

    final_strategy_balance = reward_pool.balanceOf(strategy_addr)
    assert final_strategy_balance == initial_strategy_balance + total_deposited

    for user, expected_shares in user_shares.items():
        assert vault_contract.balanceOf(user) == expected_shares


def test_vault_deposit_full_balance(
    test_permissioned_vault,
    funded_accounts,
    pyusd_pool,
    get_base_reward_pool,
):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    vault_contract = raac_vault.at(vault_addr)
    strategy_contract = strategy.at(strategy_addr)

    reward_pool = get_base_reward_pool(strategy_contract.rewards_contract())

    user = funded_accounts[0]
    user_lp_balance = pyusd_pool.balanceOf(user)

    initial_strategy_balance = reward_pool.balanceOf(strategy_addr)

    with boa.env.prank(user):
        pyusd_pool.approve(vault_addr, user_lp_balance)
        shares = vault_contract.deposit(user_lp_balance, user)

    final_strategy_balance = reward_pool.balanceOf(strategy_addr)
    assert final_strategy_balance == initial_strategy_balance + user_lp_balance
    assert vault_contract.balanceOf(user) == shares
    assert pyusd_pool.balanceOf(user) == 0


def test_vault_deposit_for_another_user(
    test_permissioned_vault,
    funded_accounts,
    pyusd_pool,
    get_base_reward_pool,
):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault
    depositor = funded_accounts[0]
    receiver = funded_accounts[1]

    vault_contract = raac_vault.at(vault_addr)
    strategy_contract = strategy.at(strategy_addr)

    reward_pool = get_base_reward_pool(strategy_contract.rewards_contract())

    depositor_lp_balance = pyusd_pool.balanceOf(depositor)
    deposit_amount = depositor_lp_balance // 2

    initial_strategy_balance = reward_pool.balanceOf(strategy_addr)
    initial_receiver_shares = vault_contract.balanceOf(receiver)
    initial_depositor_shares = vault_contract.balanceOf(depositor)

    with boa.env.prank(depositor):
        pyusd_pool.approve(vault_addr, deposit_amount)
        shares = vault_contract.deposit(deposit_amount, receiver)
        logs = vault_contract.get_logs()
        deposit_log = logs[-1]
        assert deposit_log.sender == depositor
        assert deposit_log.owner == receiver
        assert deposit_log.assets == deposit_amount
        assert deposit_log.shares == shares

    final_strategy_balance = reward_pool.balanceOf(strategy_addr)
    final_receiver_shares = vault_contract.balanceOf(receiver)
    final_depositor_shares = vault_contract.balanceOf(depositor)

    assert final_strategy_balance == initial_strategy_balance + deposit_amount
    assert final_receiver_shares == initial_receiver_shares + shares
    assert final_depositor_shares == initial_depositor_shares
    assert (
        pyusd_pool.balanceOf(depositor)
        == depositor_lp_balance - deposit_amount
    )
