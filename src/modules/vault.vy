# pragma version 0.4.3
# pragma nonreentrancy on
# @license MIT

from ethereum.ercs import IERC20
from snekmate.auth import access_control
from src.modules import erc4626
from src.modules import constants
from src.interfaces import IStrategy
from src.interfaces import IVaultFactory
from src.interfaces import IHarvester

initializes: access_control
initializes: erc4626
exports: (
    erc4626.DOMAIN_SEPARATOR,
    erc4626.allowance,
    erc4626.approve,
    erc4626.asset,
    erc4626.balanceOf,
    erc4626.convertToAssets,
    erc4626.convertToShares,
    erc4626.decimals,
    erc4626.deposit,
    erc4626.eip712Domain,
    erc4626.full_profit_unlock_date,
    erc4626.locked_shares,
    erc4626.maxDeposit,
    erc4626.maxMint,
    erc4626.maxRedeem,
    erc4626.maxWithdraw,
    erc4626.mint,
    erc4626.name,
    erc4626.nonces,
    erc4626.permit,
    erc4626.previewDeposit,
    erc4626.previewMint,
    erc4626.previewRedeem,
    erc4626.previewWithdraw,
    erc4626.profit_max_unlock_time,
    erc4626.profit_unlocking_rate,
    erc4626.raw_total_supply,
    erc4626.raw_vault_balance,
    erc4626.redeem,
    erc4626.strategy,
    erc4626.symbol,
    erc4626.totalAssets,
    erc4626.totalSupply,
    erc4626.transfer,
    erc4626.transferFrom,
    erc4626.unlock_scale,
    erc4626.unlocked_shares,
    erc4626.withdraw,
)

exports: (
    access_control.DEFAULT_ADMIN_ROLE,
    access_control.getRoleAdmin,
    access_control.grantRole,
    access_control.hasRole,
    access_control.renounceRole,
    access_control.revokeRole,
    access_control.set_role_admin,
    access_control.supportsInterface,
)


event UpdateProfitMaxUnlockTime:
    profit_max_unlock_time: uint256


last_harvest: public(uint256)

# Access control roles
STRATEGY_MANAGER_ROLE: public(constant(bytes32)) = keccak256("STRATEGY_MANAGER_ROLE")

# Can be made permissionless by setting to a permissionless proxy contract
HARVESTER_ROLE: public(constant(bytes32)) = keccak256("HARVESTER_ROLE")


@deploy
def __init__(
    _name: String[25],
    _symbol: String[5],
    _asset: IERC20,
    _decimals_offset: uint8,
    _name_eip712: String[50],
    _version_eip712: String[20],
    _strategy: address,
    _profit_max_unlock_time: uint256,
):
    """
    @dev Contract deployer will have the DEFAULT_ADMIN_ROLE on the vault
    """
    assert _strategy != empty(address), "No strategy"
    access_control.__init__()
    erc4626.__init__(
        _name,
        _symbol,
        _asset,
        _decimals_offset,
        _name_eip712,
        _version_eip712,
        _strategy,
        _profit_max_unlock_time,
    )


@external
def set_platform_fee(_new_platform_fee: uint256):
    assert access_control.hasRole[STRATEGY_MANAGER_ROLE][msg.sender]
    extcall IStrategy(erc4626.strategy).set_platform_fee(_new_platform_fee)


@external
def set_caller_fee(_new_caller_fee: uint256):
    assert access_control.hasRole[STRATEGY_MANAGER_ROLE][msg.sender]
    extcall IStrategy(erc4626.strategy).set_caller_fee(_new_caller_fee)


@external
def update_harvester(
    _new_harvester: address,
    _migration_tokens: DynArray[address, constants.MAX_REWARD_TOKENS + 2] = [],
):
    assert (
        access_control.hasRole[STRATEGY_MANAGER_ROLE][msg.sender]
        or access_control.hasRole[access_control.DEFAULT_ADMIN_ROLE][msg.sender]
    )
    harvester: address = staticcall IStrategy(erc4626.strategy).harvester()

    # Forward any stranded tokens from old to new harvester
    # This is particularly necessary for CoW harvesters where harvest rewards are delayed
    if len(_migration_tokens) > 0:
        extcall IStrategy(erc4626.strategy).forward_tokens(_migration_tokens, _new_harvester)

    factory: address = staticcall IHarvester(harvester).factory()
    extcall IStrategy(erc4626.strategy).update_harvester(_new_harvester)
    # We roll over the previous harvester's hooks by default
    target_hook: address = staticcall IHarvester(harvester).target_hook()
    extra_reward_hook: address = staticcall IHarvester(harvester).extra_reward_hook()
    if target_hook != empty(address):
        extcall IStrategy(erc4626.strategy).set_target_hook(target_hook)
    if extra_reward_hook != empty(address):
        extcall IStrategy(erc4626.strategy).set_extra_reward_hook(extra_reward_hook)

    extcall IVaultFactory(factory).update_harvester(_new_harvester)


@external
def set_extra_reward_hook(_new_hook: address):
    assert (
        access_control.hasRole[STRATEGY_MANAGER_ROLE][msg.sender]
        or access_control.hasRole[access_control.DEFAULT_ADMIN_ROLE][msg.sender]
    )
    extcall IStrategy(erc4626.strategy).set_extra_reward_hook(_new_hook)


@external
def set_target_hook(_new_hook: address):
    assert (
        access_control.hasRole[STRATEGY_MANAGER_ROLE][msg.sender]
        or access_control.hasRole[access_control.DEFAULT_ADMIN_ROLE][msg.sender]
    )
    extcall IStrategy(erc4626.strategy).set_target_hook(_new_hook)


@external
def harvest(
    _caller_fee_receiver: address,
    _min_amount_out: uint256,
    _extra_rewards: DynArray[address, constants.MAX_REWARD_TOKENS],
    _reward_hook_calldata: Bytes[4096],
    _target_hook_calldata: Bytes[4096],
    _harvester_calldata: Bytes[4096],
):
    """
    @notice Execute harvest with automatic profit streaming
    @param _caller_fee_receiver Address to receive caller fee
    @param _min_amount_out Minimum amount expected from final swap to target asset
    @param _extra_rewards Array of additional reward token addresses to swap
    @param _reward_hook_calldata Calldata to pass to extra reward hook contract
    @param _target_hook_calldata Calldata to pass to target hook contract
    @param _harvester_calldata Calldata to pass to harvester
    @dev Only callable by addresses with HARVESTER_ROLE. Profit streaming is automatic
         but can be disabled by setting profit_max_unlock_time to 0.
    """
    assert access_control.hasRole[HARVESTER_ROLE][msg.sender]

    # no harvest if no users / nothing was minted
    assert erc4626.erc20.totalSupply > 0, "No supply"

    # Capture assets before harvest for profit calculation
    pre_harvest_assets: uint256 = staticcall IStrategy(erc4626.strategy).total_assets()

    # Execute harvest
    extcall IStrategy(erc4626.strategy).harvest(
        _caller_fee_receiver,
        _min_amount_out,
        _extra_rewards,
        _reward_hook_calldata,
        _target_hook_calldata,
        _harvester_calldata,
    )

    # Calculate profit and process streaming (if enabled)
    post_harvest_assets: uint256 = staticcall IStrategy(erc4626.strategy).total_assets()
    if post_harvest_assets > pre_harvest_assets:
        profit: uint256 = post_harvest_assets - pre_harvest_assets
        erc4626._process_profit_streaming(profit, pre_harvest_assets)

    self.last_harvest = block.timestamp


@external
def set_profit_max_unlock_time(_new_profit_max_unlock_time: uint256):
    """
    @notice Set the new profit max unlock time
    @param _new_profit_max_unlock_time The new profit max unlock time in seconds
    @dev Must be less than one year for security, only callable by strategy manager
    """
    assert (
        access_control.hasRole[STRATEGY_MANAGER_ROLE][msg.sender]
        or access_control.hasRole[access_control.DEFAULT_ADMIN_ROLE][msg.sender]
    )
    # unlock time < 1 year
    assert _new_profit_max_unlock_time <= 31_556_952, "profit unlock time too long"

    # If setting to 0, unlock all profits immediately
    if _new_profit_max_unlock_time == 0:
        locked_shares: uint256 = erc4626.erc20.balanceOf[self]
        if locked_shares > 0:
            # burn locked shares to unlock profits immediately
            erc4626.erc20._burn(self, locked_shares)

        erc4626.profit_unlocking_rate = 0
        erc4626.full_profit_unlock_date = 0

    erc4626.profit_max_unlock_time = _new_profit_max_unlock_time
    log UpdateProfitMaxUnlockTime(profit_max_unlock_time=_new_profit_max_unlock_time)
