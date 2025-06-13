import boa

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
