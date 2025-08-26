# pragma version 0.4.3
"""
@title Liquidity Hook
@custom:contract-name raac_liquidity_hook
@notice RAAC Vault hook to add one-sided liquidity to a regular Curve pool
@license MIT
@author RAAC
"""

from ethereum.ercs import IERC20
from src.interfaces import ICurveStableSwap
from src.interfaces import IHarvester


@external
def add_liquidity(
    _pool_address: address,
    _token: address,
    _token_index: uint256,
    _min_amount_out: uint256,
):
    """
    @notice Add one-sided liquidity to a regular Curve pool via this hook.
    @param _pool_address The Curve pool contract address.
    @param _token The token address to provide as liquidity.
    @param _token_index The index of the token in the pool.
    @param _min_amount_out The minimum pool tokens to mint.
    @custom:reverts On failed approval or liquidity add.
    """
    amount: uint256 = staticcall IERC20(_token).balanceOf(msg.sender)
    if amount == 0:
        return
    extcall IHarvester(msg.sender).transfer_to_target_hook(_token, amount)
    extcall IERC20(_token).approve(_pool_address, 0)
    extcall IERC20(_token).approve(_pool_address, amount)

    liquidity_amounts: uint256[2] = [0, 0]
    liquidity_amounts[_token_index] = amount

    extcall ICurveStableSwap(_pool_address).add_liquidity(
        liquidity_amounts, _min_amount_out, msg.sender
    )
