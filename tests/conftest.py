from typing import Any, Callable

import boa
import moccasin
import pytest
from boa.contracts.abi.abi_contract import ABIContractFactory
from moccasin.boa_tools import VyperContract
from moccasin.config import get_config
from moccasin.moccasin_account import MoccasinAccount

from src import factory, raac_vault, strategy
from src.harvesters import cow_harvester, curve_harvester, oracle_harvester
from src.hooks import add_liquidity, add_liquidity_oracle, handle_extra_rewards
from tests.utils.abis import BASE_REWARD_POOL_ABI, CONVEX_STASH_ABI, ERC20_ABI
from tests.utils.constants import (
    CONVEX_BOOSTER,
    CONVEX_BOOSTER_OWNER,
    PYUSD_BOOSTER_ID,
    PYUSD_CONVEX_STASH,
    RSUP_STAKER_CONTRACT,
    RSUP_TOKEN,
)

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


@pytest.fixture(scope="session")
def convex_booster() -> VyperContract:
    return get_config().get_active_network().manifest_named("convex_booster")


@pytest.fixture(scope="session")
def crvusd_token() -> VyperContract:
    return get_config().get_active_network().manifest_named("crvusd_token")


@pytest.fixture(scope="session")
def crv_token() -> VyperContract:
    return get_config().get_active_network().manifest_named("crv_token")


@pytest.fixture(scope="session")
def cvx_token() -> VyperContract:
    return get_config().get_active_network().manifest_named("cvx_token")


@pytest.fixture(scope="session")
def pyusd_token() -> VyperContract:
    return get_config().get_active_network().manifest_named("pyusd_token")


@pytest.fixture(scope="session")
def cvx_eth_pool() -> VyperContract:
    return get_config().get_active_network().manifest_named("cvx_eth_pool")


@pytest.fixture(scope="session")
def tri_crv_pool() -> VyperContract:
    return get_config().get_active_network().manifest_named("tri_crv_pool")


@pytest.fixture(scope="session")
def pyusd_crvusd_pool() -> VyperContract:
    return (
        get_config().get_active_network().manifest_named("pyusd_crvusd_pool")
    )


@pytest.fixture(scope="session")
def harvester_blueprint() -> VyperContract:
    return curve_harvester.deploy_as_blueprint()


@pytest.fixture(scope="session")
def strategy_blueprint() -> VyperContract:
    return strategy.deploy_as_blueprint()


@pytest.fixture(scope="session")
def raac_vault_blueprint() -> VyperContract:
    return raac_vault.deploy_as_blueprint()


@pytest.fixture(scope="session")
def add_liquidity_hook():
    return add_liquidity.deploy()


@pytest.fixture(scope="session")
def handle_extra_rewards_hook():
    return handle_extra_rewards.deploy()


@pytest.fixture(scope="session")
def treasury() -> MoccasinAccount:
    return boa.env.generate_address()


@pytest.fixture(scope="session")
def harvest_manager() -> MoccasinAccount:
    return boa.env.generate_address()


@pytest.fixture(scope="session")
def strategy_manager() -> MoccasinAccount:
    return boa.env.generate_address()


@pytest.fixture(scope="session")
def crvusd_minter(crvusd_token):
    return crvusd_token.minter()


@pytest.fixture(scope="session")
def admin() -> MoccasinAccount:
    return moccasin.config.get_active_network().get_default_account()


@pytest.fixture(scope="session")
def accounts():
    users = []
    for i in range(10):
        user = boa.env.generate_address()
        users.append(user)
    return users


@pytest.fixture(scope="function")
def funded_accounts(accounts, crvusd_token, crvusd_minter, pyusd_crvusd_pool):
    for user in accounts:
        with boa.env.prank(crvusd_minter):
            crvusd_token.mint(user, int(100_000 * 1e18))

        amount = int(50_000 * 1e18)
        with boa.env.prank(user):
            crvusd_token.approve(pyusd_crvusd_pool.address, amount)
            pyusd_crvusd_pool.add_liquidity([0, amount], 0)

    return accounts


@pytest.fixture(scope="session")
def vault_factory(
    raac_vault_blueprint,
    strategy_blueprint,
    harvester_blueprint,
    treasury,
):
    return factory.deploy(
        raac_vault_blueprint,
        strategy_blueprint,
        harvester_blueprint,
        treasury,
    )


@pytest.fixture(scope="session")
def deploy_permissioned_vault_for_pool(
    vault_factory, harvest_manager, strategy_manager
) -> Callable[[int, str, str], tuple]:
    def inner(
        booster_id: int,
        extra_reward_hook: str = ZERO_ADDRESS,
        target_hook: str = ZERO_ADDRESS,
    ) -> tuple:
        return vault_factory.deploy_new_vault(
            booster_id,
            harvest_manager,
            strategy_manager,
            extra_reward_hook,
            target_hook,
        )

    return inner


@pytest.fixture(scope="session")
def get_base_reward_pool() -> Callable[[str], Any]:
    def inner(address: str):
        return ABIContractFactory("BaseRewardPool", BASE_REWARD_POOL_ABI).at(
            address
        )

    return inner


@pytest.fixture(scope="module")
def test_permissioned_vault(
    deploy_permissioned_vault_for_pool, add_liquidity_hook
):
    vault_addr, strategy_addr, harvester_addr = (
        deploy_permissioned_vault_for_pool(
            PYUSD_BOOSTER_ID, target_hook=add_liquidity_hook.address
        )
    )
    return vault_addr, strategy_addr, harvester_addr


@pytest.fixture(scope="module")
def set_up_extra_rewards_for_pyusd_pool(get_base_reward_pool):
    def inner(delay=0):
        # we use a delay to set up a case where no more CRV / CVX rewards
        # rewards are usually queued for a week on Convex
        if delay > 0:
            boa.env.time_travel(seconds=delay)
        stash = ABIContractFactory("StashV3", CONVEX_STASH_ABI).at(
            PYUSD_CONVEX_STASH
        )
        with boa.env.prank(CONVEX_BOOSTER_OWNER):
            stash.setExtraReward(RSUP_TOKEN)
        with boa.env.prank(RSUP_STAKER_CONTRACT):
            ABIContractFactory("ERC20", ERC20_ABI).at(RSUP_TOKEN).transfer(
                stash, int(1_000_000 * 1e18)
            )
        with boa.env.prank(CONVEX_BOOSTER):
            stash.processStash()

    return inner


@pytest.fixture(scope="module")
def test_extra_rewards_permissioned_vault(
    deploy_permissioned_vault_for_pool,
    handle_extra_rewards_hook,
    add_liquidity_hook,
):
    vault_addr, strategy_addr, harvester_addr = (
        deploy_permissioned_vault_for_pool(
            PYUSD_BOOSTER_ID,
            extra_reward_hook=handle_extra_rewards_hook,
            target_hook=add_liquidity_hook.address,
        )
    )
    return vault_addr, strategy_addr, harvester_addr


@pytest.fixture(scope="session")
def cow_harvester_blueprint() -> VyperContract:
    return cow_harvester.deploy_as_blueprint()


@pytest.fixture(scope="session")
def cow_vault_factory(
    raac_vault_blueprint,
    strategy_blueprint,
    cow_harvester_blueprint,
    treasury,
):
    return factory.deploy(
        raac_vault_blueprint,
        strategy_blueprint,
        cow_harvester_blueprint,
        treasury,
    )


@pytest.fixture(scope="session")
def deploy_cow_vault_for_pool(
    cow_vault_factory, harvest_manager, strategy_manager
) -> Callable[[int, str, str], tuple]:
    def inner(
        booster_id: int,
        extra_reward_hook: str = ZERO_ADDRESS,
        target_hook: str = ZERO_ADDRESS,
    ) -> tuple:
        return cow_vault_factory.deploy_new_vault(
            booster_id,
            harvest_manager,
            strategy_manager,
            extra_reward_hook,
            target_hook,
        )

    return inner


@pytest.fixture(scope="module")
def test_cow_vault(deploy_cow_vault_for_pool, add_liquidity_hook):
    vault_addr, strategy_addr, harvester_addr = deploy_cow_vault_for_pool(
        PYUSD_BOOSTER_ID, target_hook=add_liquidity_hook.address
    )
    return vault_addr, strategy_addr, harvester_addr


@pytest.fixture(scope="session")
def oracle_harvester_blueprint() -> VyperContract:
    return oracle_harvester.deploy_as_blueprint()


@pytest.fixture(scope="session")
def add_liquidity_oracle_hook():
    return add_liquidity_oracle.deploy()


@pytest.fixture(scope="session")
def oracle_vault_factory(
    raac_vault_blueprint,
    strategy_blueprint,
    oracle_harvester_blueprint,
    treasury,
):
    return factory.deploy(
        raac_vault_blueprint,
        strategy_blueprint,
        oracle_harvester_blueprint,
        treasury,
    )


@pytest.fixture(scope="session")
def deploy_oracle_vault_for_pool(
    oracle_vault_factory, harvest_manager, strategy_manager
) -> Callable[[int, str, str], tuple]:
    def inner(
        booster_id: int,
        extra_reward_hook: str = ZERO_ADDRESS,
        target_hook: str = ZERO_ADDRESS,
    ) -> tuple:
        return oracle_vault_factory.deploy_new_vault(
            booster_id,
            harvest_manager,
            strategy_manager,
            extra_reward_hook,
            target_hook,
        )

    return inner


@pytest.fixture(scope="module")
def test_oracle_vault(deploy_oracle_vault_for_pool, add_liquidity_oracle_hook):
    vault_addr, strategy_addr, harvester_addr = deploy_oracle_vault_for_pool(
        PYUSD_BOOSTER_ID, target_hook=add_liquidity_oracle_hook.address
    )
    return vault_addr, strategy_addr, harvester_addr
