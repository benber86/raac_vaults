# pragma version 0.4.3
# @license MIT

from src.modules.swappers import curve_swapper
from src.modules import constants

initializes: curve_swapper

exports: (
    curve_swapper.extra_reward_hook,
    curve_swapper.factory,
    curve_swapper.set_approvals,
    curve_swapper.set_extra_reward_hook,
    curve_swapper.set_strategy,
    curve_swapper.set_target_hook,
    curve_swapper.strategy,
    curve_swapper.target_hook,
    curve_swapper.transfer_to_reward_hook,
    curve_swapper.transfer_to_target_hook,
    curve_swapper.treasury,
    curve_swapper.__default__,
)


@deploy
def __init__(_factory: address):
    curve_swapper.__init__(_factory)


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
    @notice Swap accumulated CRV and CVX rewards to crvUSD
    @param _caller Address to receive caller fee
    @param _min_amount_out Minimum amount expected from final swap to target asset
                           i.e. the LP token - this is a check on the amount of tokens
                           AFTER adding liquidity with the target hook
    @param _extra_rewards Not needed for the curve harvester - the hook calldata
                          will contain the info need to process extra rewards
    @param _reward_hook_calldata Calldata to pass to extra reward hook contract
    @param _target_hook_calldata Calldata to pass to target hook contract
    @param _harvester_calldata Not needed for the curve harvester
    @return target_asset_balance Amount of target asset received
    """
    assert curve_swapper.swapper.strategy != empty(address)
    assert (msg.sender == curve_swapper.swapper.strategy), "Strategy only"
    return curve_swapper._swap(
        _caller, _min_amount_out, _reward_hook_calldata, _target_hook_calldata
    )
