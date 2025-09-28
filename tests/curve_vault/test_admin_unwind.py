import boa
import pytest

from src import raac_vault, strategy
from tests.utils.constants import POOL_MANAGER, RSUP_TOKEN


@pytest.mark.usefixtures("funded_accounts")
def test_admin_unwind_rewards(
    pyusd_vault,
    pyusd_pool,
    convex_booster,
    accounts,
    admin,
    crv_token,
    cvx_token,
    fxn_token,
    vault_factory,
    rsup_token,
):
    vault_addr, strategy_addr, _ = pyusd_vault
    vault = raac_vault.at(vault_addr)
    strat = strategy.at(strategy_addr)

    with boa.env.prank(vault_factory.address):
        vault.grantRole(vault.DEFAULT_ADMIN_ROLE(), admin.address)

    user = accounts[0]
    deposit_amount = int(1_000 * 10**18)

    with boa.env.prank(user):
        pyusd_pool.approve(vault_addr, deposit_amount)
        vault.deposit(deposit_amount, user)

    staked_before = strat.total_assets()
    assert staked_before > 0

    # Shutdown the current pool
    old_pid = strat.booster_id()
    _, _, _, _, _, old_shutdown = convex_booster.poolInfo(old_pid)
    assert not old_shutdown
    with boa.env.prank(POOL_MANAGER):
        convex_booster.shutdownPool(old_pid)
    _, _, _, _, _, is_shutdown = convex_booster.poolInfo(old_pid)
    assert is_shutdown

    boa.deal(crv_token, strat.address, int(1_000 * 10**18))
    boa.deal(cvx_token, strat.address, int(500 * 10**18))
    boa.deal(fxn_token, strat.address, int(100 * 10**18))
    boa.deal(rsup_token, strat.address, int(200 * 10**18))

    recipient = strat.harvester()

    crv_h_before = crv_token.balanceOf(recipient)
    cvx_h_before = cvx_token.balanceOf(recipient)
    fxn_h_before = fxn_token.balanceOf(recipient)
    rsup_h_before = rsup_token.balanceOf(recipient)

    # unwind — forwards CRV, CVX and provided extras from strategy to recipient
    with boa.env.prank(admin.address):
        vault.admin_unwind_rewards(recipient, [fxn_token.address, RSUP_TOKEN])

    assert crv_token.balanceOf(recipient) > crv_h_before
    assert cvx_token.balanceOf(recipient) > cvx_h_before
    assert fxn_token.balanceOf(recipient) > fxn_h_before
    assert rsup_token.balanceOf(recipient) >= rsup_h_before

    # LP staking unchanged (no LP moves during unwind)
    assert strat.total_assets() == staked_before
