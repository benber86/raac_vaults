# pragma version 0.4.3
"""
@title RAAC CoW Harvester
@custom:contract-name raac_cow_harvester
@notice Harvester contract to compound RAAC vault rewards with CoW Swap
@license MIT
@author RAAC
"""

from src.modules.swappers import cow_swapper
from src.modules import constants

initializes: cow_swapper

exports: (
    cow_swapper.COMPOSABLE_COW,
    cow_swapper.MAX_TOKENS,
    cow_swapper.VAULT_RELAYER,
    cow_swapper.cancel_order,
    cow_swapper.delay,
    cow_swapper.extra_reward_hook,
    cow_swapper.factory,
    cow_swapper.getTradeableOrder,
    cow_swapper.get_order_info,
    cow_swapper.isValidSignature,
    cow_swapper.owner,
    cow_swapper.set_approvals,
    cow_swapper.set_delay,
    cow_swapper.set_extra_reward_hook,
    cow_swapper.set_strategy,
    cow_swapper.set_target_hook,
    cow_swapper.strategy,
    cow_swapper.supportsInterface,
    cow_swapper.target_hook,
    cow_swapper.token_order_info,
    cow_swapper.transfer_to_reward_hook,
    cow_swapper.transfer_to_target_hook,
    cow_swapper.treasury,
    cow_swapper.verify,
    cow_swapper.__default__,
)


@deploy
def __init__(_factory: address):
    cow_swapper.__init__(_factory)


@external
@nonreentrant
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
    assert cow_swapper.swapper.strategy != empty(address)
    assert (msg.sender == cow_swapper.swapper.strategy), "Strategy only"
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
