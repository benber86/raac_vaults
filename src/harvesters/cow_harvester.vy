# pragma version 0.4.3
# @license MIT

from src.modules.swappers import cow_swapper
from src.modules import constants

initializes: cow_swapper

exports: cow_swapper.__interface__


@deploy
def __init__(factory_: address):
    cow_swapper.__init__(factory_)


@nonreentrant
@external
def harvest(
    _caller: address,
    _min_amount_out: uint256,
    _extra_rewards: DynArray[address, constants.MAX_REWARD_TOKENS],
    _reward_hook_calldata: Bytes[4096],
    _target_hook_calldata: Bytes[4096],
    _harvester_calldata: Bytes[4096],
) -> uint256:
    """
    @notice Swap accumulated CRV, CVX and extra reward tokens via CoW Swap
    @param _caller Address to receive caller fee
    @param _min_amount_out Minimum amount expected from final swap to target asset
                           i.e. the LP token - this is a check on the amount of tokens
                           AFTER adding liquidity with the target hook
    @param _extra_rewards Array of additional reward token addresses to swap via CoW
    @param _reward_hook_calldata Calldata to pass to extra reward hook contract
    @param _target_hook_calldata Calldata to pass to target hook contract
    @param _harvester_calldata ABI-encoded array of minimum buy amounts for each token swap
                               (DynArray[uint256, MAX_TOKENS])
                               This can't be blank and needs at least the amount for CRV and
                               CVX
    @return target_asset_balance Amount of target asset received
    """
    assert cow_swapper.swapper.fee_collector.strategy != empty(address)
    assert msg.sender == cow_swapper.swapper.fee_collector.strategy, "Strategy only"
    cow_swapper.swapper.fee_collector._collect()
    tokens_to_swap: DynArray[address, cow_swapper.MAX_TOKENS] = [
        constants.CRV_TOKEN, constants.CVX_TOKEN
    ]
    for i: uint256 in range(constants.MAX_REWARD_TOKENS):
        if i == len(_extra_rewards):
            break
        tokens_to_swap.append(_extra_rewards[i])

    buy_amounts: DynArray[uint256, cow_swapper.MAX_TOKENS] = abi_decode(
        _harvester_calldata, DynArray[uint256, cow_swapper.MAX_TOKENS]
    )
    return cow_swapper._swap(
        _caller,
        _min_amount_out,
        _reward_hook_calldata,
        _target_hook_calldata,
        tokens_to_swap,
        buy_amounts,
    )
