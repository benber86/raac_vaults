import moccasin
from moccasin.boa_tools import VyperContract
from moccasin.config import get_config

from src import factory, raac_vault, strategy
from src.harvesters import cow_harvester, curve_harvester
from src.hooks import add_liquidity
from tests.utils.constants import CRVUSD_POOLS, ZERO_ADDRESS

TREASURY = "0xaef6ea60f6443bad046e825c1d2b0c0b5ebc1f16"
deployer = moccasin.config.get_active_network().get_default_account()


def deploy() -> VyperContract:
    verifier = get_config().get_active_network().moccasin_verify
    curve_harvester_blueprint = curve_harvester.deploy_as_blueprint()
    cow_harvester_blueprint = cow_harvester.deploy_as_blueprint()
    strategy_blueprint = strategy.deploy_as_blueprint()
    raac_vault_blueprint = raac_vault.deploy_as_blueprint()
    add_liquidity_hook = add_liquidity.deploy()
    factory_deployment = factory.deploy(
        raac_vault,
        strategy,
        [
            ("curve", curve_harvester_blueprint.address),
            ("cow", cow_harvester_blueprint.address),
        ],
        TREASURY,
    )
    contracts = [
        curve_harvester_blueprint,
        cow_harvester_blueprint,
        strategy_blueprint,
        raac_vault_blueprint,
        factory_deployment,
        add_liquidity_hook,
    ]

    for contract in contracts:
        verifier(contract)
        verifier.wait_for_verification()

    factory_deployment.deploy_new_vault(
        CRVUSD_POOLS["usdt"]["booster_id"],
        1,  # cow harvester index
        deployer,  # harvest manager
        deployer,  # strategy manager
        ZERO_ADDRESS,
        add_liquidity_hook,
    )


def moccasin_main() -> VyperContract:
    return deploy()
