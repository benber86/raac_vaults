import boa

from src import strategy
from src.harvesters import curve_harvester
from tests.conftest import ZERO_ADDRESS


def test_strategy_set_extra_reward_hook(
    test_permissioned_vault, add_liquidity_hook
):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    strategy_contract = strategy.at(strategy_addr)
    harvester_contract = curve_harvester.at(harvester_addr)

    with boa.env.prank(vault_addr):
        strategy_contract.set_extra_reward_hook(add_liquidity_hook.address)

    assert harvester_contract.extra_reward_hook() == add_liquidity_hook.address


def test_strategy_set_target_hook(test_permissioned_vault, add_liquidity_hook):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    strategy_contract = strategy.at(strategy_addr)
    harvester_contract = curve_harvester.at(harvester_addr)

    with boa.env.prank(vault_addr):
        strategy_contract.set_target_hook(add_liquidity_hook.address)

    assert harvester_contract.target_hook() == add_liquidity_hook.address


def test_strategy_set_platform_fee(test_permissioned_vault):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    strategy_contract = strategy.at(strategy_addr)
    new_fee = 1500

    with boa.env.prank(vault_addr):
        strategy_contract.set_platform_fee(new_fee)

    assert strategy_contract.platform_fee() == new_fee


def test_strategy_set_caller_fee(test_permissioned_vault):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    strategy_contract = strategy.at(strategy_addr)
    new_fee = 200

    with boa.env.prank(vault_addr):
        strategy_contract.set_caller_fee(new_fee)

    assert strategy_contract.caller_fee() == new_fee


def test_strategy_update_harvester(test_permissioned_vault, accounts):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    strategy_contract = strategy.at(strategy_addr)
    new_harvester = accounts[5]

    with boa.env.prank(vault_addr):
        strategy_contract.update_harvester(new_harvester)

    assert strategy_contract.harvester() == new_harvester


def test_strategy_set_platform_fee_reverts_too_high(test_permissioned_vault):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    strategy_contract = strategy.at(strategy_addr)

    with boa.env.prank(vault_addr):
        with boa.reverts():
            strategy_contract.set_platform_fee(10000)


def test_strategy_set_caller_fee_reverts_too_high(test_permissioned_vault):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    strategy_contract = strategy.at(strategy_addr)

    with boa.env.prank(vault_addr):
        with boa.reverts():
            strategy_contract.set_caller_fee(10000)


def test_strategy_set_platform_fee_reverts_non_vault(
    test_permissioned_vault, accounts
):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    strategy_contract = strategy.at(strategy_addr)
    non_vault = accounts[1]

    with boa.env.prank(non_vault):
        with boa.reverts():
            strategy_contract.set_platform_fee(1500)


def test_strategy_set_caller_fee_reverts_non_vault(
    test_permissioned_vault, accounts
):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    strategy_contract = strategy.at(strategy_addr)
    non_vault = accounts[1]

    with boa.env.prank(non_vault):
        with boa.reverts():
            strategy_contract.set_caller_fee(200)


def test_strategy_update_harvester_reverts_non_vault(
    test_permissioned_vault, accounts
):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    strategy_contract = strategy.at(strategy_addr)
    non_vault = accounts[1]

    with boa.env.prank(non_vault):
        with boa.reverts():
            strategy_contract.update_harvester(accounts[5])


def test_strategy_update_harvester_reverts_zero_address(
    test_permissioned_vault,
):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    strategy_contract = strategy.at(strategy_addr)

    with boa.env.prank(vault_addr):
        with boa.reverts():
            strategy_contract.update_harvester(ZERO_ADDRESS)


def test_strategy_set_extra_reward_hook_reverts_non_vault(
    test_permissioned_vault, accounts, add_liquidity_hook
):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    strategy_contract = strategy.at(strategy_addr)
    non_vault = accounts[1]

    with boa.env.prank(non_vault):
        with boa.reverts():
            strategy_contract.set_extra_reward_hook(add_liquidity_hook.address)


def test_strategy_set_target_hook_reverts_non_vault(
    test_permissioned_vault, accounts, add_liquidity_hook
):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    strategy_contract = strategy.at(strategy_addr)
    non_vault = accounts[1]

    with boa.env.prank(non_vault):
        with boa.reverts():
            strategy_contract.set_target_hook(add_liquidity_hook.address)


def test_strategy_deposit_reverts_non_vault(test_permissioned_vault, accounts):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    strategy_contract = strategy.at(strategy_addr)
    non_vault = accounts[1]

    with boa.env.prank(non_vault):
        with boa.reverts():
            strategy_contract.deposit(1000)


def test_strategy_withdraw_reverts_non_vault(
    test_permissioned_vault, accounts
):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    strategy_contract = strategy.at(strategy_addr)
    non_vault = accounts[1]

    with boa.env.prank(non_vault):
        with boa.reverts():
            strategy_contract.withdraw(1000, non_vault)


def test_strategy_harvest_reverts_non_vault(test_permissioned_vault, accounts):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    strategy_contract = strategy.at(strategy_addr)
    non_vault = accounts[1]

    with boa.env.prank(non_vault):
        with boa.reverts():
            strategy_contract.harvest(accounts[2], 0, [], b"", b"", b"")


def test_strategy_set_vault_reverts_already_set(
    test_permissioned_vault, accounts
):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    strategy_contract = strategy.at(strategy_addr)

    with boa.reverts():
        strategy_contract.set_vault(accounts[1])


def test_strategy_set_vault_reverts_zero_address():
    fresh_strategy = strategy.deploy(
        ZERO_ADDRESS, ZERO_ADDRESS, ZERO_ADDRESS, 0
    )
    with boa.reverts():
        fresh_strategy.set_vault(ZERO_ADDRESS)


def test_strategy_forward_tokens(test_permissioned_vault, accounts):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    strategy_contract = strategy.at(strategy_addr)
    recipient = accounts[5]
    tokens_to_forward = [accounts[6], accounts[7]]

    with boa.env.prank(vault_addr):
        strategy_contract.forward_tokens(tokens_to_forward, recipient)


def test_strategy_forward_tokens_reverts_non_vault(
    test_permissioned_vault, accounts
):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    strategy_contract = strategy.at(strategy_addr)
    non_vault = accounts[1]
    recipient = accounts[5]
    tokens_to_forward = [accounts[6], accounts[7]]

    with boa.env.prank(non_vault):
        with boa.reverts():
            strategy_contract.forward_tokens(tokens_to_forward, recipient)
