# pragma version ^0.4.1
# @license MIT

from ..modules import oracle_swapper
from ..modules import constants

initializes: oracle_swapper

exports: oracle_swapper.__interface__


@deploy
def __init__(factory_: address):
    oracle_swapper.__init__(factory_)


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
    @notice Swap accumulated CRV and CVX rewards to target asset with oracle protection
    @param _caller Address to receive caller fee
    @param _min_amount_out Minimum amount expected from final swap to target asset
    @param _extra_rewards Array of additional reward token addresses (processed via hook)
    @param _reward_hook_calldata Calldata to pass to extra reward hook contract
    @param _target_hook_calldata Calldata to pass to target hook contract
    @param _harvester_calldata Not used in oracle harvester
    @return target_asset_balance Amount of target asset received
    @dev Uses Curve pool oracles to protect against MEV/sandwich attacks
    @dev Chainlink oracle is used for crvUSD price validation
    """
    assert oracle_swapper.swapper.fee_collector.strategy != empty(address), "Strategy not set"
    assert msg.sender == oracle_swapper.swapper.fee_collector.strategy, "Strategy only"

    return oracle_swapper._swap(
        _caller, _min_amount_out, _reward_hook_calldata, _target_hook_calldata
    )
