from typing import Any, Callable

import boa
import moccasin
import pytest
from boa.contracts.abi.abi_contract import ABIContractFactory
from moccasin.boa_tools import VyperContract
from moccasin.config import get_config
from moccasin.moccasin_account import MoccasinAccount

from src import factory, raac_vault, strategy
from src.harvesters import cow_harvester, curve_harvester
from src.hooks import add_liquidity, add_liquidity_ng, handle_extra_rewards
from src.mocks import mock_strategy
from tests.utils.abis import (
    BASE_REWARD_POOL_ABI,
    CONVEX_STASH_ABI,
    CURVE_STABLESWAP_ABI,
    CURVE_STABLESWAP_NG_ABI,
)
from tests.utils.constants import (
    CONVEX_BOOSTER,
    CONVEX_BOOSTER_OWNER,
    CRVUSD_POOLS,
    FXN_TOKEN,
    RSUP_STAKER_CONTRACT,
    RSUP_TOKEN,
    ZERO_ADDRESS,
)

# Pool name constants for parametrization
PYUSD_POOL_NAME = "pyusd"
USDC_POOL_NAME = "usdc"
USDT_POOL_NAME = "usdt"


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
def fxn_token() -> VyperContract:
    return get_config().get_active_network().manifest_named("fxn_token")


@pytest.fixture(scope="session")
def rsup_token() -> VyperContract:
    return get_config().get_active_network().manifest_named("rsup_token")


@pytest.fixture(scope="session")
def cvx_eth_pool() -> VyperContract:
    return get_config().get_active_network().manifest_named("cvx_eth_pool")


@pytest.fixture(scope="session")
def tri_crv_pool() -> VyperContract:
    return get_config().get_active_network().manifest_named("tri_crv_pool")


@pytest.fixture(scope="session")
def pyusd_pool() -> VyperContract:
    return ABIContractFactory("CurvePool", CURVE_STABLESWAP_NG_ABI).at(
        CRVUSD_POOLS[PYUSD_POOL_NAME]["pool_address"]
    )


@pytest.fixture(scope="session")
def usdc_pool() -> VyperContract:
    return ABIContractFactory("CurvePool", CURVE_STABLESWAP_ABI).at(
        CRVUSD_POOLS[USDC_POOL_NAME]["pool_address"]
    )


@pytest.fixture(scope="session")
def usdt_pool() -> VyperContract:
    return ABIContractFactory("CurvePool", CURVE_STABLESWAP_ABI).at(
        CRVUSD_POOLS[USDT_POOL_NAME]["pool_address"]
    )


@pytest.fixture(scope="session")
def pool_list(pyusd_pool, usdc_pool, usdt_pool):
    return {
        PYUSD_POOL_NAME: pyusd_pool,
        USDC_POOL_NAME: usdc_pool,
        USDT_POOL_NAME: usdt_pool,
    }


@pytest.fixture(scope="session")
def crvusd_pool(pyusd_pool) -> VyperContract:
    return pyusd_pool


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
def add_liquidity_ng_hook():
    return add_liquidity_ng.deploy()


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
def funded_accounts(accounts, crvusd_token, crvusd_minter, pool_list):
    for user in accounts:
        with boa.env.prank(crvusd_minter):
            crvusd_token.mint(user, int(1_000_000 * len(pool_list) * 1e18))

        amount = int(500_000 * 1e18)
        for pool_name, pool_contract in pool_list.items():
            with boa.env.prank(user):
                crvusd_token.approve(pool_contract.address, amount)
                amounts = [0, 0]
                amounts[CRVUSD_POOLS[pool_name]["crvusd_index"]] = amount
                pool_contract.add_liquidity(amounts, 0)

    return accounts


@pytest.fixture(scope="session")
def vault_factory(
    raac_vault_blueprint,
    strategy_blueprint,
    harvester_blueprint,
    cow_harvester_blueprint,
    treasury,
):
    harvesters = [
        ("curve", harvester_blueprint.address),
        ("cow", cow_harvester_blueprint.address),
    ]
    return factory.deploy(
        raac_vault_blueprint,
        strategy_blueprint,
        harvesters,
        treasury,
    )


@pytest.fixture(scope="session")
def deploy_permissioned_vault_for_pool(
    vault_factory, harvest_manager, strategy_manager
) -> Callable[[str, str, str], tuple]:
    def inner(
        pool_name: str,
        extra_reward_hook: str = ZERO_ADDRESS,
        target_hook: str = ZERO_ADDRESS,
    ) -> tuple:
        return vault_factory.deploy_new_vault(
            CRVUSD_POOLS[pool_name]["booster_id"],
            0,  # curve harvester index
            harvest_manager,
            strategy_manager,
            extra_reward_hook,
            target_hook,
            0,
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
def pyusd_vault(deploy_permissioned_vault_for_pool, add_liquidity_ng_hook):
    vault_addr, strategy_addr, harvester_addr = (
        deploy_permissioned_vault_for_pool(
            PYUSD_POOL_NAME, target_hook=add_liquidity_ng_hook.address
        )
    )
    return vault_addr, strategy_addr, harvester_addr


@pytest.fixture(scope="module")
def usdc_vault(deploy_permissioned_vault_for_pool, add_liquidity_hook):
    vault_addr, strategy_addr, harvester_addr = (
        deploy_permissioned_vault_for_pool(
            USDC_POOL_NAME, target_hook=add_liquidity_hook.address
        )
    )
    return vault_addr, strategy_addr, harvester_addr


@pytest.fixture(scope="module")
def usdt_vault(deploy_permissioned_vault_for_pool, add_liquidity_hook):
    vault_addr, strategy_addr, harvester_addr = (
        deploy_permissioned_vault_for_pool(
            USDT_POOL_NAME, target_hook=add_liquidity_hook.address
        )
    )
    return vault_addr, strategy_addr, harvester_addr


@pytest.fixture(scope="module")
def vault_list(pyusd_vault, usdc_vault, usdt_vault):
    return {
        PYUSD_POOL_NAME: pyusd_vault,
        USDC_POOL_NAME: usdc_vault,
        USDT_POOL_NAME: usdt_vault,
    }


@pytest.fixture(scope="module")
def test_permissioned_vault(pyusd_vault):
    return pyusd_vault


@pytest.fixture(scope="module")
def set_up_extra_rewards_for_pool(
    get_base_reward_pool, pool_list, fxn_token, rsup_token
):
    def inner(delay=0):
        if delay > 0:
            boa.env.time_travel(seconds=delay)

        for pool_name in pool_list.keys():
            stash = ABIContractFactory("StashV3", CONVEX_STASH_ABI).at(
                CRVUSD_POOLS[pool_name]["convex_stash"]
            )
            with boa.env.prank(CONVEX_BOOSTER_OWNER):
                stash.setExtraReward(RSUP_TOKEN)
                stash.setExtraReward(FXN_TOKEN)
            with boa.env.prank(RSUP_STAKER_CONTRACT):
                rsup_token.transfer(stash, int(1_000_000 * 1e18))
            boa.deal(fxn_token, stash.address, int(1_000_000 * 1e18))
            with boa.env.prank(CONVEX_BOOSTER):
                stash.processStash()

    return inner


@pytest.fixture(scope="module")
def pyusd_extra_rewards_vault(
    deploy_permissioned_vault_for_pool,
    handle_extra_rewards_hook,
    add_liquidity_ng_hook,
):
    vault_addr, strategy_addr, harvester_addr = (
        deploy_permissioned_vault_for_pool(
            PYUSD_POOL_NAME,
            extra_reward_hook=handle_extra_rewards_hook,
            target_hook=add_liquidity_ng_hook.address,
        )
    )
    return vault_addr, strategy_addr, harvester_addr


@pytest.fixture(scope="module")
def usdc_extra_rewards_vault(
    deploy_permissioned_vault_for_pool,
    handle_extra_rewards_hook,
    add_liquidity_hook,
):
    vault_addr, strategy_addr, harvester_addr = (
        deploy_permissioned_vault_for_pool(
            USDC_POOL_NAME,
            extra_reward_hook=handle_extra_rewards_hook,
            target_hook=add_liquidity_hook.address,
        )
    )
    return vault_addr, strategy_addr, harvester_addr


@pytest.fixture(scope="module")
def usdt_extra_rewards_vault(
    deploy_permissioned_vault_for_pool,
    handle_extra_rewards_hook,
    add_liquidity_hook,
):
    vault_addr, strategy_addr, harvester_addr = (
        deploy_permissioned_vault_for_pool(
            USDT_POOL_NAME,
            extra_reward_hook=handle_extra_rewards_hook,
            target_hook=add_liquidity_hook.address,
        )
    )
    return vault_addr, strategy_addr, harvester_addr


@pytest.fixture(scope="module")
def extra_rewards_vault_list(
    pyusd_extra_rewards_vault, usdc_extra_rewards_vault
):
    return {
        PYUSD_POOL_NAME: pyusd_extra_rewards_vault,
        USDC_POOL_NAME: usdc_extra_rewards_vault,
    }


@pytest.fixture(scope="module")
def test_extra_rewards_permissioned_vault(pyusd_extra_rewards_vault):
    return pyusd_extra_rewards_vault


@pytest.fixture(scope="session")
def cow_harvester_blueprint() -> VyperContract:
    return cow_harvester.deploy_as_blueprint()


@pytest.fixture(scope="session")
def deploy_cow_vault_for_pool(
    vault_factory, harvest_manager, strategy_manager
) -> Callable[[str, str, str], tuple]:
    def inner(
        pool_name: str,
        extra_reward_hook: str = ZERO_ADDRESS,
        target_hook: str = ZERO_ADDRESS,
    ) -> tuple:
        return vault_factory.deploy_new_vault(
            CRVUSD_POOLS[pool_name]["booster_id"],
            1,  # cow harvester index
            harvest_manager,
            strategy_manager,
            extra_reward_hook,
            target_hook,
            0,
        )

    return inner


@pytest.fixture(scope="module")
def pyusd_cow_vault(deploy_cow_vault_for_pool, add_liquidity_ng_hook):
    vault_addr, strategy_addr, harvester_addr = deploy_cow_vault_for_pool(
        PYUSD_POOL_NAME, target_hook=add_liquidity_ng_hook.address
    )
    return vault_addr, strategy_addr, harvester_addr


@pytest.fixture(scope="module")
def usdc_cow_vault(deploy_cow_vault_for_pool, add_liquidity_hook):
    vault_addr, strategy_addr, harvester_addr = deploy_cow_vault_for_pool(
        USDC_POOL_NAME, target_hook=add_liquidity_hook.address
    )
    return vault_addr, strategy_addr, harvester_addr


@pytest.fixture(scope="module")
def usdt_cow_vault(deploy_cow_vault_for_pool, add_liquidity_hook):
    vault_addr, strategy_addr, harvester_addr = deploy_cow_vault_for_pool(
        USDT_POOL_NAME, target_hook=add_liquidity_hook.address
    )
    return vault_addr, strategy_addr, harvester_addr


@pytest.fixture(scope="module")
def cow_vault_list(pyusd_cow_vault, usdc_cow_vault, usdt_cow_vault):
    return {
        PYUSD_POOL_NAME: pyusd_cow_vault,
        USDC_POOL_NAME: usdc_cow_vault,
        USDT_POOL_NAME: usdt_cow_vault,
    }


@pytest.fixture(scope="module")
def test_cow_vault(pyusd_cow_vault):
    return pyusd_cow_vault


@pytest.fixture(scope="session")
def mock_strategy_contract(crvusd_token):
    return mock_strategy.deploy(crvusd_token.address)


@pytest.fixture(scope="session")
def mock_vault(crvusd_token, mock_strategy_contract):
    vault_instance = raac_vault.deploy(
        "RAAC Mock Vault",
        "MOCK",
        crvusd_token.address,
        0,
        "RAAC Mock Vault",
        "1",
        mock_strategy_contract.address,
        604800,
    )

    mock_strategy_contract.set_vault(vault_instance.address)
    return vault_instance


@pytest.fixture(scope="function")
def funded_mock_vault_users(mock_vault, crvusd_token, accounts):
    for user in accounts:
        boa.deal(crvusd_token, user, int(1_000_000 * 1e18))
        with boa.env.prank(user):
            crvusd_token.approve(mock_vault.address, int(1_000_000 * 1e18))

    return accounts


@pytest.fixture(scope="session")
def harvest_caller(mock_strategy_contract, mock_vault, crvusd_token):
    caller = boa.env.generate_address()
    boa.deal(crvusd_token, caller, int(1_000_000_000 * 1e18))
    with boa.env.prank(caller):
        crvusd_token.approve(mock_strategy_contract.address, 2**256 - 1)

    mock_vault.grantRole(mock_vault.HARVESTER_ROLE(), caller)
    mock_vault.grantRole(mock_vault.STRATEGY_MANAGER_ROLE(), caller)
    return caller
