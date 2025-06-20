import pytest

from src import raac_vault, strategy
from src.harvesters import curve_harvester
from tests.conftest import ZERO_ADDRESS
from tests.utils.constants import PYUSD_BOOSTER_ID


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
    pyusd_crvusd_pool,
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
            PYUSD_BOOSTER_ID,
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
    assert rec.booster_id == PYUSD_BOOSTER_ID
    assert rec.token != ZERO_ADDRESS

    assert strategy_contract.vault() == vault_address
    assert vault_contract.strategy() == strategy_address
    assert harvester_contract.strategy() == strategy_address
    assert harvester_contract.factory() == vault_factory.address

    expected_treasury = vault_factory.treasury()
    assert expected_treasury == treasury

    assert harvester_contract.extra_reward_hook() == extra_hook_addr
    assert harvester_contract.target_hook() == target_hook_addr

    assert vault_contract.symbol() == str(PYUSD_BOOSTER_ID)
    assert vault_contract.name() == "RAAC " + pyusd_crvusd_pool.name()[:20]


def test_vault_deployment_reverts_for_large_booster_id(
    vault_factory, harvest_manager, strategy_manager
):
    with pytest.raises(Exception):
        vault_factory.deploy_new_vault(
            10000000,
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
            2, harvest_manager, strategy_manager, ZERO_ADDRESS, ZERO_ADDRESS
        )
