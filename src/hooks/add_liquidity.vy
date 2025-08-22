# pragma version 0.4.3
"""
@title RAAC Vault hook to add one-sided liquidity to an NG Curve pool
@custom:contract-name raac_add_liquidity_hook
@license MIT
@author benny
"""

from ethereum.ercs import IERC20
from src.interfaces import ICurveStableSwapNG
from src.interfaces import IHarvester

MAX_COINS: constant(uint256) = 8


@external
def add_liquidity(
    _pool_address: address,
    _token: address,
    _token_index: uint256,
    _min_amount_out: uint256,
):
    """
    @notice Add one-sided liquidity to a Curve NG pool via this hook.
    @param _pool_address The Curve NG pool contract address.
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
    liquidity_amounts: DynArray[uint256, MAX_COINS] = empty(DynArray[uint256, MAX_COINS])
    for i: uint256 in range(MAX_COINS):
        if i == _token_index:
            liquidity_amounts.append(amount)
            break
        liquidity_amounts.append(0)

    extcall ICurveStableSwapNG(_pool_address).add_liquidity(
        liquidity_amounts, _min_amount_out, msg.sender
    )
