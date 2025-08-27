# pragma version 0.4.3
# pragma nonreentrancy on
# @license MIT

"""
@title RAAC Convex Strategy
@custom:contract-name raac_convex_strategy
@author RAAC
@notice A strategy contract for managing Convex Finance positions
@dev This contract acts as an intermediary between a vault and the Convex Booster,
     handling deposits, withdrawals, reward collection, and harvesting operations.
     It integrates with a separate harvester contract to process and swap rewards.
     It is stand alone so that harvest logic can be upgraded in case of need.
     Separating from the vault also potentially makes migrations possible although
     this is not currently implemented.
     The admin functions are only callable by the vault, where role based access is
     managed.

"""

from ethereum.ercs import IERC20
from src.modules import constants
from src.interfaces import IBooster
from src.interfaces import IConvexStaking
from src.interfaces import IBasicRewards
from src.interfaces import IHarvester

# The LP token being managed by this strategy
asset: public(reentrant(immutable(address)))
# Contract handling the processing of rewards
harvester: public(reentrant(address))
# Convex pool ID for deposits
booster_id: public(immutable(uint256))
# Convex staking contract for this pool
rewards_contract: public(immutable(address))
# Fee taken by the platform (basis points)
platform_fee: public(reentrant(uint256))
# Fee paid to harvest callers (basis points)
caller_fee: public(reentrant(uint256))
# Vault contract that owns the strategy
vault: public(reentrant(address))


event HarvesterUpdated:
    new_harvester: address


event CallerFeeUpdated:
    caller_fee: uint256


event PlatformFeeUpdated:
    platform_fee: uint256


event VaultSet:
    vault: address


@deploy
def __init__(
    _asset: address,
    _rewards_contract: address,
    _harvester: address,
    _booster_id: uint256,
):
    """
    @param _asset Address of the LP token this strategy will manage
    @param _rewards_contract Address of the Convex staking contract for rewards
    @param _harvester Address of the harvester contract for processing rewards
    @param _booster_id Convex pool ID for depositing into the booster
    @dev Sets initial platform fee to 20% and caller fee to 1%
    """

    booster_id = _booster_id
    rewards_contract = _rewards_contract
    asset = _asset
    self.harvester = _harvester
    self.platform_fee = 2000  # 20%
    self.caller_fee = 100  # 1%


@external
def set_approvals():
    """
    @notice Set target token approvals for the Curve Booster
    @dev Callable by anyone to reset
    """
    assert extcall IERC20(asset).approve(constants.CONVEX_BOOSTER, 0, default_return_value=True)
    assert extcall IERC20(asset).approve(
        constants.CONVEX_BOOSTER, max_value(uint256), default_return_value=True
    )


@external
def set_vault(_vault: address):
    """
    @notice Set the vault address that will control this strategy
    @param _vault Address of the vault contract
    @dev Can only be called once when vault is not yet set
    @dev This is permissionless because strategy deployment is bundled with
         vault creation in the factory so can't be front-ran
    @dev Vault cannot be the zero address
    """
    assert self.vault == empty(address), "Vault already set"
    assert _vault != empty(address), "Vault can't be empty"
    self.vault = _vault
    log VaultSet(vault=_vault)


@external
def set_platform_fee(_platform_fee: uint256):
    """
    @notice Update the platform fee percentage
    @param _platform_fee New platform fee in basis points (e.g., 2000 = 20%)
    """
    assert msg.sender == self.vault, "Vault only"
    assert _platform_fee < constants.MAX_PLATFORM_FEE, "Fee too high"
    self.platform_fee = _platform_fee
    log PlatformFeeUpdated(platform_fee=_platform_fee)


@external
def set_caller_fee(_caller_fee: uint256):
    """
    @notice Update the caller fee percentage paid to harvest initiators to pay for gas
    @param _caller_fee New caller fee in basis points (e.g., 100 = 1%)
    """
    assert msg.sender == self.vault, "Vault only"
    assert _caller_fee < constants.MAX_CALLER_FEE, "Fee too high"
    self.caller_fee = _caller_fee
    log CallerFeeUpdated(caller_fee=_caller_fee)


@external
def update_harvester(_harvester: address):
    """
    @notice Update the harvester contract address
    @param _harvester Address of the new harvester contract
    """
    assert msg.sender == self.vault, "Vault only"
    assert _harvester != empty(address), "Zero address"
    self.harvester = _harvester
    log HarvesterUpdated(new_harvester=_harvester)


@external
def set_extra_reward_hook(_new_hook: address):
    """
    @notice Set a hook contract in the harvester for processing extra reward tokens
    @param _new_hook Address of the hook contract to handle additional rewards
    """
    assert msg.sender == self.vault, "Vault only"
    extcall IHarvester(self.harvester).set_extra_reward_hook(_new_hook)


@external
def set_target_hook(_new_hook: address):
    """
    @notice Set a target hook contract in the harvester for handling the swap from
            rewards to the target LP token
    @param _new_hook Address of the target hook contract
    """
    assert msg.sender == self.vault, "Vault only"
    extcall IHarvester(self.harvester).set_target_hook(_new_hook)


@external
def deposit(_amount: uint256):
    """
    @notice Deposit LP tokens into the Convex strategy
    @param _amount Amount of LP tokens to deposit
    """
    assert msg.sender == self.vault, "Vault only"
    self._deposit(_amount)


@external
def withdraw(_amount: uint256, _receiver: address):
    """
    @notice Withdraw LP tokens from the Convex strategy
    @param _amount Amount of LP tokens to withdraw
    @param _receiver Address who will receive the withdrawn tokens
    """
    assert msg.sender == self.vault, "Vault only"
    # No need to claim rewards on withdrawal as they are for the whole vault
    # and can be claimed during next harvest
    extcall IConvexStaking(rewards_contract).withdrawAndUnwrap(_amount, False)
    assert extcall IERC20(asset).transfer(
        _receiver, _amount, default_return_value=True
    ), "erc4626: transfer operation did not succeed"


@external
@view
def total_assets() -> uint256:
    """
    @notice Get the total amount of underlying assets managed by this strategy
    @return The total balance of LP tokens staked in the Convex rewards contract
    @dev This represents assets actively earning rewards, unstaked tokens not included
    """
    return staticcall IBasicRewards(rewards_contract).balanceOf(self)


@internal
def _deposit(_amount: uint256):
    extcall IBooster(constants.CONVEX_BOOSTER).deposit(booster_id, _amount, True)


@internal
def _forward_rewards(_reward_tokens: DynArray[address, constants.MAX_REWARD_TOKENS]):
    """
    @notice Forward collected reward tokens to the harvester contract
    @param _reward_tokens Array of reward token addresses to forward
    @dev Transfers the entire balance of each reward token to the harvester
    """
    for i: uint256 in range(constants.MAX_REWARD_TOKENS):
        if i == len(_reward_tokens):
            break
        reward_balance: uint256 = staticcall IERC20(_reward_tokens[i]).balanceOf(self)
        if reward_balance > 0:
            assert extcall IERC20(_reward_tokens[i]).transfer(
                self.harvester, reward_balance, default_return_value=True
            )


@internal
def _collect(_extra_rewards: DynArray[address, constants.MAX_REWARD_TOKENS]):
    """
    @notice Collect all available rewards from the Convex staking contract
    @param _extra_rewards Array of additional reward token addresses beyond CRV/CVX
    @dev Always forwards CRV and CVX tokens, plus any specified extra rewards
    """
    # claim rewards from the staking contract
    extcall IBasicRewards(rewards_contract).getReward()
    # forward CRV and CVX rewards to the harvester
    self._forward_rewards([constants.CVX_TOKEN, constants.CRV_TOKEN])
    if len(_extra_rewards) > 0:
        self._forward_rewards(_extra_rewards)


@external
def harvest(
    _caller: address,
    _min_amount_out: uint256,
    _extra_rewards: DynArray[address, constants.MAX_REWARD_TOKENS],
    _reward_hook_calldata: Bytes[4096],
    _target_hook_calldata: Bytes[4096],
    _harvester_calldata: Bytes[4096],
):
    """
    @notice Harvest rewards and compound them back into the strategy
    @param _min_amount_out Minimum amount of target asset expected from harvesting
    @param _caller Address of the account initiating the harvest (for the caller fee)
    @param _extra_rewards Array of additional reward token addresses to collect
    @param _reward_hook_calldata Calldata to pass to the reward processing hook
    @param _target_hook_calldata Calldata to pass to the target processing hook
    @param _harvester_calldata Calldata to pass to the harvester (Optional)
    @dev Collects rewards, processes them via harvester, and re-deposits the result
    @dev The harvester handles the actual reward swapping, fee collection, and
         distribution
    """
    assert msg.sender == self.vault, "Vault only"
    self._collect(_extra_rewards)
    target_asset_balance: uint256 = extcall IHarvester(self.harvester).harvest(
        _caller,
        _min_amount_out,
        _extra_rewards,
        _reward_hook_calldata,
        _target_hook_calldata,
        _harvester_calldata,
    )
    if target_asset_balance > 0:
        self._deposit(target_asset_balance)


@external
def forward_tokens(
    _tokens: DynArray[address, constants.MAX_REWARD_TOKENS + 2], _recipient: address
):
    """
    @notice Forward tokens from current harvester to recipient for migration
    @param _tokens Array of token addresses to forward
    @param _recipient Address to receive tokens
    @dev Only callable by vault for harvester migration
    """
    assert msg.sender == self.vault, "Vault only"
    extcall IHarvester(self.harvester).forward_tokens(_tokens, _recipient)
