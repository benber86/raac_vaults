import boa


def test_deposit_withdraw_three_users(
    mock_vault, mock_strategy_contract, funded_mock_vault_users, crvusd_token
):
    vault = mock_vault
    users = funded_mock_vault_users[:3]
    deposit_amounts = [
        100_000 * 10**18,
        200_000 * 10**18,
        150_000 * 10**18,
    ]

    # All users deposit
    shares_received = []
    for i, user in enumerate(users):
        amount = deposit_amounts[i]
        initial_balance = crvusd_token.balanceOf(user)

        with boa.env.prank(user):
            shares = vault.deposit(amount, user)

        shares_received.append(shares)
        assert crvusd_token.balanceOf(user) == initial_balance - amount
        assert vault.balanceOf(user) == shares
        assert vault.totalAssets() == mock_strategy_contract.total_assets()

    # All users withdraw
    for i, user in enumerate(users):
        initial_balance = crvusd_token.balanceOf(user)
        shares = shares_received[i]

        with boa.env.prank(user):
            assets_received = vault.redeem(shares, user, user)

        assert assets_received == deposit_amounts[i]
        assert (
            crvusd_token.balanceOf(user)
            == initial_balance + deposit_amounts[i]
        )
        assert vault.balanceOf(user) == 0
        assert vault.totalAssets() == mock_strategy_contract.total_assets()
