# pragma version ^0.4.1
"""
@title RAAC Vault hook to process extra reward tokens using Curve Router
@custom:contract-name raac_extra_reward_hook
@license MIT
@author benny
"""

from ethereum.ercs import IERC20
from ..interfaces import ICurveRouter
from ..interfaces import IHarvester
from ..interfaces import IStrategy
from ..modules import constants

CURVE_ROUTER: constant(address) = 0x45312ea0eFf7E09C83CBE249fa1d7598c4C8cd4e


@external
def process_extra_rewards(
    _token: address, _route: address[11], _swap_params: uint256[5][5], _pools: address[5]
):
    """
    @notice Process extra reward tokens by swapping them to crvUSD via Curve Router and applying platform fees
    @param _token The extra reward token address to process
    @param _route Array of [initial token, pool, token, pool, token, ...] for Curve Router
    @param _swap_params Multidimensional array of [i, j, swap_type, pool_type, n_coins] for each swap
    @param _pools Array of pools for swaps via zap contracts (for meta-factories)
    @custom:reverts On failed swaps or transfers
    """
    amount: uint256 = staticcall IERC20(_token).balanceOf(msg.sender)
    extcall IHarvester(msg.sender).transfer_to_reward_hook(_token, amount)

    # Get harvester info
    harvester: address = msg.sender
    strategy: address = staticcall IHarvester(harvester).strategy()
    treasury: address = staticcall IHarvester(harvester).treasury()
    platform_fee: uint256 = staticcall IStrategy(strategy).platform_fee()

    # Approve token for Curve Router
    assert extcall IERC20(_token).approve(CURVE_ROUTER, 0, default_return_value=True)
    assert extcall IERC20(_token).approve(CURVE_ROUTER, amount, default_return_value=True)

    # Execute swap via Curve Router
    crvusd_received: uint256 = extcall ICurveRouter(CURVE_ROUTER).exchange(
        _route, _swap_params, amount, 0, _pools, self  # We'll handle slippage after fees
    )

    # Apply platform fee
    platform_fee_amount: uint256 = crvusd_received * platform_fee // 10000
    remaining_amount: uint256 = crvusd_received - platform_fee_amount

    # Transfer platform fee to treasury
    if platform_fee_amount > 0:
        assert extcall IERC20(constants.CRVUSD_TOKEN).transfer(
            treasury, platform_fee_amount, default_return_value=True
        ), "Treasury transfer failed"

    if remaining_amount > 0:
        assert extcall IERC20(constants.CRVUSD_TOKEN).transfer(
            harvester, remaining_amount, default_return_value=True
        ), "Harvester transfer failed"
