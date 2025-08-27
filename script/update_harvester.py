import moccasin
from boa.contracts.vyper.vyper_contract import VyperBlueprint
from moccasin.boa_tools import VyperContract
from moccasin.config import get_config

from src import factory, raac_vault, strategy
from src.harvesters import cow_harvester, curve_harvester
from src.hooks import add_liquidity
from tests.utils.constants import CRVUSD_POOLS, ZERO_ADDRESS

TREASURY = "0xaef6ea60f6443bad046e825c1d2b0c0b5ebc1f16"
FACTORY = ""
deployer = moccasin.config.get_active_network().get_default_account()


def _verify(contract):
    verifier = get_config().get_active_network().moccasin_verify(contract)
    verifier.wait_for_verification()


def deploy() -> VyperContract:

    harvester = cow_harvester.deploy()
    vault = raac_vault.at("0xaf4cf126040e78ca408c55b6f052048afb2218f6")

    strategy_blueprint = strategy.deploy_as_blueprint()
    raac_vault_blueprint = raac_vault.deploy_as_blueprint()
    add_liquidity_hook = add_liquidity.deploy()
    factory_deployment = factory.deploy(
        raac_vault_blueprint.address,
        strategy_blueprint.address,
        [
            ("curve", curve_harvester_blueprint.address),
            ("cow", cow_harvester_blueprint.address),
        ],
        TREASURY,
    )

    contracts = [
        factory_deployment,
        curve_harvester_blueprint,
        cow_harvester_blueprint,
        strategy_blueprint,
        raac_vault_blueprint,
        add_liquidity_hook,
    ]

    for contract in contracts:
        print(f"Verifying: {contract} ({type(contract)})")
        _verify(contract)

    factory_deployment.deploy_new_vault(
        CRVUSD_POOLS["usdt"]["booster_id"],
        1,  # cow harvester index
        deployer.address,  # harvest manager
        deployer.address,  # strategy manager
        ZERO_ADDRESS,
        add_liquidity_hook.address,
    )


def moccasin_main() -> VyperContract:
    return deploy()
