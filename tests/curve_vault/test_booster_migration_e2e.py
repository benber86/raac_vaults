import boa
import pytest
from boa.util.abi import abi_encode
from eth_utils import function_signature_to_4byte_selector

from src import raac_vault, strategy
from tests.utils.constants import (
    CRVUSD_POOLS,
    FXN_TOKEN,
    POOL_MANAGER,
    RSUP_TOKEN,
)


@pytest.mark.usefixtures("funded_accounts")
def test_booster_migration_e2e(
    pyusd_vault,
    pyusd_pool,
    convex_booster,
    accounts,
    strategy_manager,
    harvest_manager,
    crv_token,
    cvx_token,
    fxn_token,
    crvusd_token,
    rsup_token,
):
    vault_addr, strategy_addr, _ = pyusd_vault
    vault_contract = raac_vault.at(vault_addr)
    strategy_contract = strategy.at(strategy_addr)

    user = accounts[0]
    asset = vault_contract.asset()
    deposit_amount = int(1_000 * 10**18)

    with boa.env.prank(user):
        pyusd_pool.approve(vault_contract.address, deposit_amount)
        vault_contract.deposit(deposit_amount, user)

    initial_pid = strategy_contract.booster_id()
    staked_before = strategy_contract.total_assets()
    assert staked_before > 0

    lptoken, _, gauge, old_rewards, _, old_shutdown = convex_booster.poolInfo(
        initial_pid
    )
    assert lptoken == asset
    assert old_shutdown is False

    with boa.env.prank(POOL_MANAGER):
        convex_booster.shutdownPool(initial_pid)
    _, _, _, _, _, is_shutdown = convex_booster.poolInfo(initial_pid)
    assert is_shutdown is True

    with boa.env.prank(POOL_MANAGER):
        convex_booster.addPool(lptoken, gauge, 3)

    new_pid = convex_booster.poolLength() - 1
    new_lptoken, _, new_gauge, new_rewards, _, new_shutdown = (
        convex_booster.poolInfo(new_pid)
    )
    assert new_lptoken == lptoken
    assert new_gauge == gauge
    assert new_shutdown is False

    harvester = strategy_contract.harvester()

    boa.deal(crv_token, strategy_contract.address, int(5_000 * 10**18))
    boa.deal(cvx_token, strategy_contract.address, int(2_000 * 10**18))
    boa.deal(fxn_token, strategy_contract.address, int(500 * 10**18))
    boa.deal(rsup_token, strategy_contract.address, int(500 * 10**18))

    crv_h_before = crv_token.balanceOf(harvester)
    cvx_h_before = cvx_token.balanceOf(harvester)
    fxn_h_before = fxn_token.balanceOf(harvester)
    rsup_h_before = rsup_token.balanceOf(harvester)

    with boa.env.prank(strategy_manager):
        vault_contract.migrate_booster(new_pid, [RSUP_TOKEN, FXN_TOKEN])

    assert strategy_contract.booster_id() == new_pid
    assert strategy_contract.rewards_contract() == new_rewards

    staked_after = strategy_contract.total_assets()
    assert staked_after == pytest.approx(staked_before, rel=1e-6)

    assert crv_token.balanceOf(harvester) > crv_h_before
    assert cvx_token.balanceOf(harvester) > cvx_h_before
    assert fxn_token.balanceOf(harvester) > fxn_h_before
    assert rsup_token.balanceOf(harvester) >= rsup_h_before
    sig = "add_liquidity(address,address,uint256,uint256)"
    selector = function_signature_to_4byte_selector(sig)
    encoded_args = abi_encode(
        "(address,address,uint256,uint256)",
        [
            CRVUSD_POOLS["pyusd"]["pool_address"],
            crvusd_token.address,
            CRVUSD_POOLS["pyusd"]["crvusd_index"],
            0,
        ],
    )
    target_hook_calldata = selector + encoded_args

    ta_before = strategy_contract.total_assets()
    with boa.env.prank(harvest_manager):
        vault_contract.harvest(
            harvest_manager, 0, [], b"", target_hook_calldata, b""
        )
    ta_after = strategy_contract.total_assets()
    assert ta_after >= ta_before
