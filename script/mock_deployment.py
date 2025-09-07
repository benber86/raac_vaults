import moccasin
from moccasin.boa_tools import VyperContract
from moccasin.config import get_config

from src import factory, raac_vault, strategy
from src.harvesters import cow_harvester, curve_harvester
from src.hooks import add_liquidity
from tests.utils.constants import CRVUSD_POOLS, ZERO_ADDRESS

TREASURY = "0xaef6ea60f6443bad046e825c1d2b0c0b5ebc1f16"
deployer = moccasin.config.get_active_network().get_default_account()


def deploy_as_blueprint(contract: VyperContract, name: str) -> VyperContract:
    print(f"Deploying {name} as blueprint")

    for attempt in range(3):
        try:
            return contract.deploy_as_blueprint()
        except Exception as e:
            print(f"Attempt {attempt + 1} failed for {name} blueprint: {e}")
            if attempt == 2:
                raise


def deploy_contract(
    contract: VyperContract, name: str, *args, **kwargs
) -> VyperContract:
    print(f"Deploying {name}")

    for attempt in range(3):
        try:
            return contract.deploy(*args, **kwargs)
        except Exception as e:
            print(f"Attempt {attempt + 1} failed for {name}: {e}")
            if attempt == 2:
                raise


def _verify(contract):
    print(f"Verifying {contract}")

    for attempt in range(3):
        try:
            verifier = (
                get_config().get_active_network().moccasin_verify(contract)
            )
            verifier.wait_for_verification()
            print(f"Successfully verified {contract}")
            return
        except Exception as e:
            print(f"Attempt {attempt + 1} failed to verify {contract}: {e}")
            if attempt == 2:
                print(f"Failed to verify {contract} after 3 attempts")
                return


def deploy() -> VyperContract:

    curve_harvester_blueprint = deploy_as_blueprint(
        curve_harvester, "Curve Harvester"
    )
    cow_harvester_blueprint = deploy_as_blueprint(
        cow_harvester, "CoW Harvester"
    )
    strategy_blueprint = deploy_as_blueprint(strategy, "Strategy")
    raac_vault_blueprint = deploy_as_blueprint(raac_vault, "RAAC Vault")
    add_liquidity_hook = deploy_contract(add_liquidity, "Add Liquidity Hook")
    factory_deployment = deploy_contract(
        factory,
        "Factory",
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

    factory_deployment.deploy_new_vault(
        CRVUSD_POOLS["usdt"]["booster_id"],
        1,  # cow harvester index
        deployer.address,  # harvest manager
        deployer.address,  # strategy manager
        ZERO_ADDRESS,
        add_liquidity_hook.address,
        0,
    )

    for contract in contracts:
        _verify(contract)


def moccasin_main() -> VyperContract:
    return deploy()
