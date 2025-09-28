import moccasin
from boa.contracts.abi.abi_contract import ABIContractFactory

from script.mock_deployment import _verify
from src import factory, raac_vault
from src.harvesters import cow_harvester
from tests.utils.abis import ERC20_ABI
from tests.utils.constants import CRV_TOKEN, CVX_TOKEN

TREASURY = "0xaef6ea60f6443bad046e825c1d2b0c0b5ebc1f16"
FACTORY = "0xE1Ca332516A74e136575bac99205C60888982989"
STRATEGY = "0xc3A520c4dBA00D14a4d3E5AA1719de7878f9cFE5"
VAULT = "0x66B849ae48EdFeADaE3684f9bCB0EB8565a21EF8"
CURRENT_HARVESTER = "0x7E96eCB7D835f52328Bf929e83DF103C6022aA46"
deployer = moccasin.config.get_active_network().get_default_account()


def deploy():

    new_harvester_blueprint = cow_harvester.deploy_as_blueprint()
    factory_contract = factory.at(FACTORY)
    factory_contract.add_harvester("cow v2", new_harvester_blueprint.address)
    new_harvester = factory_contract.deploy_harvester_instance(
        factory_contract.harvester_count() - 1, VAULT
    )
    _verify(cow_harvester.at(new_harvester))
    print(f"New harvester deployed at {new_harvester}")
    vault = raac_vault.at(VAULT)
    cvx_token = ABIContractFactory("ERC20", ERC20_ABI).at(CVX_TOKEN)
    crv_token = ABIContractFactory("ERC20", ERC20_ABI).at(CRV_TOKEN)
    print(
        f"Balance of CRV of old harvester: {crv_token.balanceOf(CURRENT_HARVESTER)}"
    )
    print(
        f"Balance of CVX of old harvester: {cvx_token.balanceOf(CURRENT_HARVESTER)}"
    )
    vault.update_harvester(new_harvester, [CRV_TOKEN, CVX_TOKEN])
    print(
        f"Balance of CRV of new harvester: {crv_token.balanceOf(new_harvester)}"
    )
    print(
        f"Balance of CVX of new harvester: {cvx_token.balanceOf(new_harvester)}"
    )
    print()


def moccasin_main():
    return deploy()
