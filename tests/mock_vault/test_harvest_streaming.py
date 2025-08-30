import boa
import pytest


def test_harvest_streaming_rewards(
    mock_vault,
    mock_strategy_contract,
    funded_mock_vault_users,
    harvest_caller,
    crvusd_token,
):
    user1, user2 = funded_mock_vault_users[0], funded_mock_vault_users[1]

    deposit_amount = int(100_000 * 1e18)

    with boa.env.prank(user1):
        shares1 = mock_vault.deposit(deposit_amount, user1)

    with boa.env.prank(user2):
        shares2 = mock_vault.deposit(deposit_amount, user2)

    total_deposited = deposit_amount * 2
    total_shares_before = shares1 + shares2

    print("Initial state:")
    print(f"Total deposited: {total_deposited / 1e18:.1f}")
    print(f"Total shares: {total_shares_before / 1e18:.1f}")
    print(f"Total assets: {mock_vault.totalAssets() / 1e18:.1f}")

    harvest_amount = int(50_000 * 1e18)

    expected_locked_shares = mock_vault.convertToShares(harvest_amount)
    print(f"Expected locked shares: {expected_locked_shares / 1e18:.1f}")

    with boa.env.prank(harvest_caller):
        mock_vault.harvest(harvest_caller, harvest_amount, [], b"", b"", b"")

    print("\nAfter harvest:")
    print(f"Total assets: {mock_vault.totalAssets() / 1e18:.1f}")
    print(f"Unlocked shares: {mock_vault.unlocked_shares() / 1e18:.1f}")
    print(
        f"Locked shares: {mock_vault.balanceOf(mock_vault.address) / 1e18:.1f}"
    )
    print(f"Full profit unlock date: {mock_vault.full_profit_unlock_date()}")

    assert mock_vault.totalAssets() == total_deposited + harvest_amount
    assert mock_vault.unlocked_shares() == 0
    assert mock_vault.balanceOf(mock_vault.address) == pytest.approx(
        expected_locked_shares, rel=1e-3
    )
    expected_total_supply = total_shares_before + expected_locked_shares
    assert mock_vault.totalSupply() == pytest.approx(
        expected_total_supply, rel=1e-3
    )

    streaming_period = mock_vault.profit_max_unlock_time()
    print(f"Streaming period: {streaming_period} seconds")

    user1_max_withdraw_start = mock_vault.maxWithdraw(user1)
    user2_max_withdraw_start = mock_vault.maxWithdraw(user2)

    print("\nAt start of streaming:")
    print(f"User1 max withdraw: {user1_max_withdraw_start / 1e18:.1f}")
    print(f"User2 max withdraw: {user2_max_withdraw_start / 1e18:.1f}")

    assert user1_max_withdraw_start == pytest.approx(deposit_amount, rel=1e-3)
    assert user2_max_withdraw_start == pytest.approx(deposit_amount, rel=1e-3)

    boa.env.time_travel(seconds=streaming_period // 2)

    user1_max_withdraw_half = mock_vault.maxWithdraw(user1)
    user2_max_withdraw_half = mock_vault.maxWithdraw(user2)

    print("\nAt half streaming period:")
    print(f"User1 max withdraw: {user1_max_withdraw_half / 1e18:.1f}")
    print(f"User2 max withdraw: {user2_max_withdraw_half / 1e18:.1f}")
    print(f"Unlocked shares: {mock_vault.unlocked_shares() / 1e18:.1f}")
    print(
        f"Locked shares: {mock_vault.balanceOf(mock_vault.address) / 1e18:.1f}"
    )

    expected_half = (
        shares1 * mock_vault.totalAssets() // mock_vault.totalSupply()
    )
    assert user1_max_withdraw_half == pytest.approx(expected_half, rel=1e-6)
    assert user2_max_withdraw_half == pytest.approx(expected_half, rel=1e-6)

    boa.env.time_travel(seconds=streaming_period // 2)

    user1_max_withdraw_end = mock_vault.maxWithdraw(user1)
    user2_max_withdraw_end = mock_vault.maxWithdraw(user2)

    print("\nAt end of streaming period:")
    print(f"User1 max withdraw: {user1_max_withdraw_end / 1e18:.1f}")
    print(f"User2 max withdraw: {user2_max_withdraw_end / 1e18:.1f}")
    print(f"Unlocked shares: {mock_vault.unlocked_shares() / 1e18:.1f}")
    print(
        f"Locked shares: {mock_vault.balanceOf(mock_vault.address) / 1e18:.1f}"
    )

    expected_end = (
        shares1 * mock_vault.totalAssets() // mock_vault.totalSupply()
    )
    assert user1_max_withdraw_end == pytest.approx(expected_end, rel=1e-6)
    assert user2_max_withdraw_end == pytest.approx(expected_end, rel=1e-6)

    assert mock_vault.balanceOf(mock_vault.address) == 0

    boa.env.time_travel(seconds=streaming_period)

    print("\nAfter streaming period:")
    print(f"Unlocked shares: {mock_vault.unlocked_shares() / 1e18:.1f}")
    print(
        f"Locked shares: {mock_vault.balanceOf(mock_vault.address) / 1e18:.1f}"
    )

    final_expected = (
        shares1 * mock_vault.totalAssets() // mock_vault.totalSupply()
    )
    assert mock_vault.maxWithdraw(user1) == pytest.approx(
        final_expected, rel=1e-6
    )
    assert mock_vault.maxWithdraw(user2) == pytest.approx(
        final_expected, rel=1e-6
    )
    assert mock_vault.balanceOf(mock_vault.address) == 0
