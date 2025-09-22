import boa
import pytest

# Note: MIN_SHARES is 1e12 in the contract (raw units, not 1e18-scaled)
MIN_SHARES_RAW = 10**12


@pytest.fixture(scope="function")
def fresh_vault(crvusd_token):
    strategy = boa.load("src/mocks/mock_strategy.vy", crvusd_token.address)
    vault = boa.load(
        "src/raac_vault.vy",
        "RAAC Mock Vault",
        "MOCK",
        crvusd_token.address,
        0,
        "RAAC Mock Vault",
        "1",
        strategy.address,
        604800,
    )
    strategy.set_vault(vault.address)
    return vault


def test_deposit_below_min_shares_reverts(fresh_vault, crvusd_token, accounts):
    mock_vault = fresh_vault
    user = accounts[0]

    # deposit an amount that would mint < MIN_SHARES shares on a fresh vault
    tiny_assets = MIN_SHARES_RAW - 1  # raw wei

    # ensure user has balance and approval
    boa.deal(crvusd_token, user, tiny_assets)
    with boa.env.prank(user):
        crvusd_token.approve(mock_vault.address, tiny_assets)

        with pytest.raises(Exception, match="erc4626: deposit too small"):
            mock_vault.deposit(tiny_assets, user)


def test_mint_below_min_shares_reverts(fresh_vault, crvusd_token, accounts):
    mock_vault = fresh_vault
    user = accounts[0]

    # mint fewer than MIN_SHARES on a fresh vault
    tiny_shares = MIN_SHARES_RAW - 1  # raw wei-shares

    # ensure user has enough balance for the required assets and approval
    # previewMint with empty vault roughly equals shares:assets 1:1
    req_assets = mock_vault.previewMint(tiny_shares)
    boa.deal(crvusd_token, user, req_assets)
    with boa.env.prank(user):
        crvusd_token.approve(mock_vault.address, req_assets)

        with pytest.raises(Exception, match="erc4626: deposit too small"):
            mock_vault.mint(tiny_shares, user)


def test_withdraw_cannot_leave_supply_between_1_and_min(
    fresh_vault, crvusd_token, accounts
):
    mock_vault = fresh_vault
    user = accounts[0]

    # First, create a tiny-but-valid supply just above MIN_SHARES
    start_assets = (
        MIN_SHARES_RAW + 1
    )  # should mint ~ same shares on fresh vault
    boa.deal(crvusd_token, user, start_assets)
    with boa.env.prank(user):
        crvusd_token.approve(mock_vault.address, start_assets)
        mock_vault.deposit(start_assets, user)

    raw_before = mock_vault.raw_total_supply()
    assert raw_before >= MIN_SHARES_RAW + 1

    # Attempt to withdraw 2 shares worth of assets, which would drop the
    # raw supply to MIN_SHARES_RAW - 1 (non-zero and below min) and should revert.
    two_shares_assets = mock_vault.previewRedeem(2)
    with boa.env.prank(user):
        with pytest.raises(Exception, match="erc4626: deposit too small"):
            mock_vault.withdraw(two_shares_assets, user, user)

    # But redeeming everything to zero supply should succeed
    user_shares = mock_vault.balanceOf(user)
    with boa.env.prank(user):
        mock_vault.redeem(user_shares, user, user)
    assert mock_vault.raw_total_supply() == 0
