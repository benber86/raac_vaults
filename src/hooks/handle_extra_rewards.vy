# pragma version 0.4.3
"""
@title Extra Rewards Hook
@custom:contract-name raac_extra_reward_hook
@notice RAAC Vault hook to process extra reward tokens using Curve Router
@license MIT
@author RAAC
"""

from ethereum.ercs import IERC20
from src.interfaces import ICurveRouter
from src.interfaces import IHarvester
from src.interfaces import IStrategy
from src.modules import constants

CURVE_ROUTER: constant(address) = 0x45312ea0eFf7E09C83CBE249fa1d7598c4C8cd4e


struct ExtraRewardParams:
    token: address
    route: address[11]
    swap_params: uint256[5][5]
    pools: address[5]


@external
def process_extra_rewards(
    _rewards: DynArray[ExtraRewardParams, constants.MAX_REWARD_TOKENS],
):
    """
    @notice Process multiple extra reward tokens by swapping them to crvUSD via Curve Router
    @param _rewards Array of reward token parameters containing token address and routing info
    @custom:reverts On failed swaps or transfers
    """
    harvester: address = msg.sender

    for i: uint256 in range(constants.MAX_REWARD_TOKENS):
        if i == len(_rewards):
            break

        reward: ExtraRewardParams = _rewards[i]
        amount: uint256 = staticcall IERC20(reward.token).balanceOf(msg.sender)

        if amount == 0:
            continue

        extcall IHarvester(msg.sender).transfer_to_reward_hook(reward.token, amount)

        # Approve token for Curve Router
        assert extcall IERC20(reward.token).approve(CURVE_ROUTER, 0, default_return_value=True)
        assert extcall IERC20(reward.token).approve(CURVE_ROUTER, amount, default_return_value=True)

        # Execute swap via Curve Router
        # All crvUSD is sent directly to harvester for unified fee processing
        crvusd_received: uint256 = extcall ICurveRouter(CURVE_ROUTER).exchange(
            reward.route,
            reward.swap_params,
            amount,
            0,
            reward.pools,
            harvester,
        )
