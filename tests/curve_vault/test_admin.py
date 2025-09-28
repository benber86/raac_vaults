import boa

from src import raac_vault, strategy
from src.harvesters import curve_harvester


def test_vault_update_harvester(
    test_permissioned_vault, accounts, vault_factory, strategy_manager
):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    vault_contract = raac_vault.at(vault_addr)
    strategy_contract = strategy.at(strategy_addr)
    new_harvester = vault_factory.deploy_harvester_instance(0, vault_addr)

    vault_id = vault_factory.vault_to_id(vault_addr)

    initial_vault_record = vault_factory.vault_registry(vault_id)
    assert initial_vault_record.harvester == harvester_addr
    assert initial_vault_record.vault == vault_addr

    with boa.env.prank(strategy_manager):
        vault_contract.update_harvester(new_harvester)

    assert strategy_contract.harvester() == new_harvester

    updated_vault_record = vault_factory.vault_registry(vault_id)
    assert updated_vault_record.harvester == new_harvester
    assert updated_vault_record.vault == vault_addr
    assert updated_vault_record.strategy == strategy_addr
    assert updated_vault_record.booster_id == initial_vault_record.booster_id
    assert updated_vault_record.token == initial_vault_record.token


def test_vault_set_platform_fee(test_permissioned_vault, strategy_manager):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    vault_contract = raac_vault.at(vault_addr)
    strategy_contract = strategy.at(strategy_addr)
    new_platform_fee = 500

    with boa.env.prank(strategy_manager):
        vault_contract.set_platform_fee(new_platform_fee)

    assert strategy_contract.platform_fee() == new_platform_fee


def test_vault_set_caller_fee(test_permissioned_vault, strategy_manager):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    vault_contract = raac_vault.at(vault_addr)
    strategy_contract = strategy.at(strategy_addr)
    new_caller_fee = 100

    with boa.env.prank(strategy_manager):
        vault_contract.set_caller_fee(new_caller_fee)

    assert strategy_contract.caller_fee() == new_caller_fee


def test_vault_set_extra_reward_hook(
    test_permissioned_vault, strategy_manager, accounts
):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    vault_contract = raac_vault.at(vault_addr)
    harvester_contract = curve_harvester.at(harvester_addr)
    new_hook = accounts[6]

    with boa.env.prank(strategy_manager):
        vault_contract.set_extra_reward_hook(new_hook)

    assert harvester_contract.extra_reward_hook() == new_hook


def test_vault_set_target_hook(
    test_permissioned_vault, strategy_manager, accounts
):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    vault_contract = raac_vault.at(vault_addr)
    harvester_contract = curve_harvester.at(harvester_addr)
    new_hook = accounts[7]

    with boa.env.prank(strategy_manager):
        vault_contract.set_target_hook(new_hook)

    assert harvester_contract.target_hook() == new_hook


def test_vault_migrate_booster(test_permissioned_vault, strategy_manager):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    vault_contract = raac_vault.at(vault_addr)

    new_booster_id = 999

    # Should revert because the current pool is not shutdown on Booster
    with boa.reverts():
        with boa.env.prank(strategy_manager):
            vault_contract.migrate_booster(new_booster_id)


def test_vault_unauthorized_access(test_permissioned_vault, accounts):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    vault_contract = raac_vault.at(vault_addr)
    unauthorized_user = accounts[8]
    new_harvester = accounts[5]

    with boa.reverts():
        with boa.env.prank(unauthorized_user):
            vault_contract.update_harvester(new_harvester)

    with boa.reverts():
        with boa.env.prank(unauthorized_user):
            vault_contract.set_platform_fee(500)

    with boa.reverts():
        with boa.env.prank(unauthorized_user):
            vault_contract.migrate_booster(999)
