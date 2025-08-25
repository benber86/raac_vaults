import boa

from src.harvesters import curve_harvester
from tests.conftest import ZERO_ADDRESS


def test_factory_ownership_transfer(vault_factory, accounts):
    owner = vault_factory.owner()
    new_owner = accounts[1]
    with boa.env.prank(owner):
        vault_factory.transfer_ownership(new_owner)
        assert vault_factory.owner() == new_owner


def test_factory_ownership_renounce(vault_factory, admin):
    owner = vault_factory.owner()
    with boa.env.prank(owner):
        vault_factory.renounce_ownership()
        assert vault_factory.owner() == ZERO_ADDRESS


def test_set_treasury_by_owner(vault_factory, accounts):
    owner = vault_factory.owner()
    new_treasury = accounts[2]
    original_treasury = vault_factory.treasury()
    with boa.env.prank(owner):
        vault_factory.set_treasury(new_treasury)
    assert vault_factory.treasury() == new_treasury
    assert vault_factory.treasury() != original_treasury


def test_set_treasury_reverts_non_owner(vault_factory, accounts):
    non_owner = accounts[1]
    new_treasury = accounts[2]

    with boa.env.prank(non_owner):
        with boa.reverts():
            vault_factory.set_treasury(new_treasury)


def test_ownership_transfer_reverts_non_owner(vault_factory, accounts):
    non_owner = accounts[1]
    new_owner = accounts[2]

    with boa.env.prank(non_owner):
        with boa.reverts():
            vault_factory.transfer_ownership(new_owner)


def test_renounce_ownership_reverts_non_owner(vault_factory, accounts):
    non_owner = accounts[1]

    with boa.env.prank(non_owner):
        with boa.reverts():
            vault_factory.renounce_ownership()


def test_add_harvester_by_owner(vault_factory, accounts):
    owner = vault_factory.owner()
    new_harvester_impl = curve_harvester.deploy_as_blueprint()
    protocol = "balancer"

    initial_count = vault_factory.harvester_count()

    with boa.env.prank(owner):
        vault_factory.add_harvester(protocol, new_harvester_impl.address)

    assert vault_factory.harvester_count() == initial_count + 1
    new_harvester = vault_factory.harvesters(initial_count)
    assert new_harvester.protocol == protocol
    assert new_harvester.implementation == new_harvester_impl.address


def test_add_harvester_reverts_non_owner(vault_factory, accounts):
    non_owner = accounts[1]
    new_harvester_impl = curve_harvester.deploy_as_blueprint()

    with boa.env.prank(non_owner):
        with boa.reverts():
            vault_factory.add_harvester("balancer", new_harvester_impl.address)


def test_add_harvester_reverts_empty_address(vault_factory, accounts):
    owner = vault_factory.owner()

    with boa.env.prank(owner):
        with boa.reverts("Implementation cannot be empty"):
            vault_factory.add_harvester("balancer", ZERO_ADDRESS)


def test_harvesters_getter(vault_factory):
    harvester_0 = vault_factory.harvesters(0)
    harvester_1 = vault_factory.harvesters(1)

    assert harvester_0.protocol == "curve"
    assert harvester_1.protocol == "cow"
    assert harvester_0.implementation != ZERO_ADDRESS
    assert harvester_1.implementation != ZERO_ADDRESS


def test_harvester_count(vault_factory):
    count = vault_factory.harvester_count()
    assert count == 2

    owner = vault_factory.owner()
    new_harvester_impl = curve_harvester.deploy_as_blueprint()

    with boa.env.prank(owner):
        vault_factory.add_harvester("test", new_harvester_impl.address)

    assert vault_factory.harvester_count() == count + 1


def test_update_harvester_reverts_empty_address(vault_factory, pyusd_vault):
    vault_addr, strategy_addr, harvester_addr = pyusd_vault

    with boa.env.prank(vault_addr):
        with boa.reverts("Invalid harvester"):
            vault_factory.update_harvester(ZERO_ADDRESS)
