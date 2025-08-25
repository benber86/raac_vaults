import pytest
from boa.contracts.abi.abi_contract import ABIContractFactory

from src import raac_vault, strategy
from src.harvesters import cow_harvester, curve_harvester
from tests.conftest import ZERO_ADDRESS
from tests.utils.abis import CURVE_STABLESWAP_ABI
from tests.utils.constants import CRVUSD_POOLS


@pytest.mark.parametrize(
    "extra_reward_hook,target_hook",
    [
        ("add_liquidity_hook", "add_liquidity_hook"),
        (ZERO_ADDRESS, "add_liquidity_hook"),
        ("add_liquidity_hook", ZERO_ADDRESS),
        (ZERO_ADDRESS, ZERO_ADDRESS),
    ],
)
def test_vault_deployment_with_hooks(
    vault_factory,
    harvest_manager,
    strategy_manager,
    add_liquidity_hook,
    extra_reward_hook,
    target_hook,
    crvusd_pool,
    treasury,
):
    def resolve_hook(hook_param):
        if hook_param == "add_liquidity_hook":
            return add_liquidity_hook.address
        else:
            return hook_param

    extra_hook_addr = resolve_hook(extra_reward_hook)
    target_hook_addr = resolve_hook(target_hook)

    vault_address, strategy_address, harvester_address = (
        vault_factory.deploy_new_vault(
            CRVUSD_POOLS["pyusd"]["booster_id"],
            0,  # curve harvester index
            harvest_manager,
            strategy_manager,
            extra_hook_addr,
            target_hook_addr,
        )
    )

    event = vault_factory.get_logs()[-1]
    assert event.vault == vault_address
    assert event.strategy == strategy_address
    assert event.harvester == harvester_address

    vault_contract = raac_vault.at(vault_address)
    strategy_contract = strategy.at(strategy_address)
    harvester_contract = curve_harvester.at(harvester_address)

    idx = vault_factory.vaults_deployed()
    rec = vault_factory.vault_registry(idx)
    assert rec.vault == vault_address
    assert rec.strategy == strategy_address
    assert rec.harvester == harvester_address
    assert rec.booster_id == CRVUSD_POOLS["pyusd"]["booster_id"]
    assert rec.token != ZERO_ADDRESS

    assert strategy_contract.vault() == vault_address
    assert vault_contract.strategy() == strategy_address
    assert harvester_contract.strategy() == strategy_address
    assert harvester_contract.factory() == vault_factory.address

    expected_treasury = vault_factory.treasury()
    assert expected_treasury == treasury

    assert harvester_contract.extra_reward_hook() == extra_hook_addr
    assert harvester_contract.target_hook() == target_hook_addr

    assert vault_contract.symbol() == str(CRVUSD_POOLS["pyusd"]["booster_id"])
    assert vault_contract.name() == "RAAC-" + crvusd_pool.symbol()[:20]


def test_vault_deployment_reverts_for_large_booster_id(
    vault_factory, harvest_manager, strategy_manager
):
    with pytest.raises(Exception):
        vault_factory.deploy_new_vault(
            10000000,
            0,  # curve harvester index
            harvest_manager,
            strategy_manager,
            ZERO_ADDRESS,
            ZERO_ADDRESS,
        )


def test_vault_deployment_reverts_for_shutdown_pool(
    vault_factory, harvest_manager, strategy_manager
):
    with pytest.raises(Exception):
        vault_factory.deploy_new_vault(
            2, 0, harvest_manager, strategy_manager, ZERO_ADDRESS, ZERO_ADDRESS
        )


@pytest.mark.parametrize("pool_name", ["pyusd"])
def test_parametrized_vault_deployment(
    vault_factory,
    harvest_manager,
    strategy_manager,
    add_liquidity_hook,
    treasury,
    pool_name,
):
    pool_contract = ABIContractFactory("CurvePool", CURVE_STABLESWAP_ABI).at(
        CRVUSD_POOLS[pool_name]["pool_address"]
    )

    vault_address, strategy_address, harvester_address = (
        vault_factory.deploy_new_vault(
            CRVUSD_POOLS[pool_name]["booster_id"],
            0,  # curve harvester index
            harvest_manager,
            strategy_manager,
            ZERO_ADDRESS,
            add_liquidity_hook.address,
        )
    )

    vault_contract = raac_vault.at(vault_address)
    assert vault_contract.symbol() == str(
        CRVUSD_POOLS[pool_name]["booster_id"]
    )
    assert vault_contract.name() == "RAAC-" + pool_contract.symbol()[:20]


def test_vault_deployment_reverts_invalid_harvester_index(
    vault_factory, harvest_manager, strategy_manager
):
    with pytest.raises(Exception, match="Invalid harvester index"):
        vault_factory.deploy_new_vault(
            CRVUSD_POOLS["pyusd"]["booster_id"],
            10,  # invalid harvester index
            harvest_manager,
            strategy_manager,
            ZERO_ADDRESS,
            ZERO_ADDRESS,
        )


def test_cow_vault_deployment(
    vault_factory,
    harvest_manager,
    strategy_manager,
    add_liquidity_hook,
    crvusd_pool,
    treasury,
):
    vault_address, strategy_address, harvester_address = (
        vault_factory.deploy_new_vault(
            CRVUSD_POOLS["pyusd"]["booster_id"],
            1,  # cow harvester index
            harvest_manager,
            strategy_manager,
            ZERO_ADDRESS,
            add_liquidity_hook.address,
        )
    )

    # Verify it's a cow harvester
    harvester_contract = cow_harvester.at(harvester_address)
    assert harvester_contract.strategy() == strategy_address
    assert harvester_contract.factory() == vault_factory.address

    # Verify other standard properties
    vault_contract = raac_vault.at(vault_address)
    strategy_contract = strategy.at(strategy_address)

    assert strategy_contract.vault() == vault_address
    assert vault_contract.strategy() == strategy_address
    assert vault_contract.symbol() == str(CRVUSD_POOLS["pyusd"]["booster_id"])
    assert vault_contract.name() == "RAAC-" + crvusd_pool.symbol()[:20]
