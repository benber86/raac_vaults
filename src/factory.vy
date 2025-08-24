# pragma version 0.4.3
# @license MIT

"""
@title Factory for deploying RAAC stablecoin vaults on top of Convex
@custom:contract-name raac_vault_factory
@license MIT
@author benny
@notice Deploys ERC4626 vaults to autocompound yield from Convex positions
@dev Factory creates three interconnected contracts per deployment:
     - Vault: Manages user deposits/withdrawals with ERC4626 compliance
     - Strategy: Handles Convex staking, reward collection, and compounding
     - Harvester: Processes rewards, swaps tokens, and distributes platform fees
     Each vault targets a specific Convex Booster pool and automatically compounds
     CRV/CVX rewards back into the underlying LP position.
"""

from src.modules import constants
from src.modules.utils import conversion
from src.interfaces import IStrategy
from src.interfaces import IVault
from src.interfaces import IBooster
from src.interfaces import IHarvester
from snekmate.auth import ownable
from src import strategy


interface IERC20Detailed:
    def symbol() -> String[20]: view


initializes: ownable
exports: (ownable.transfer_ownership, ownable.renounce_ownership, ownable.owner)


struct VaultRecord:
    vault: address
    booster_id: uint256
    strategy: address
    harvester: address
    token: address


event VaultDeployed:
    id: uint256
    vault: address
    strategy: address
    harvester: address
    token: address


event TreasuryUpdated:
    treasury: address


VAULT_IMPLEMENTATION: public(immutable(address))
STRATEGY_IMPLEMENTATION: public(immutable(address))
HARVESTER_IMPLEMENTATION: public(immutable(address))

treasury: public(address)

vault_registry: public(HashMap[uint256, VaultRecord])
vaults_deployed: public(uint256)
vault_to_id: public(HashMap[address, uint256])


@deploy
def __init__(
    _vault_impl: address,
    _strategy_impl: address,
    _harvester_impl: address,
    _treasury: address,
):
    """
    @param _vault_impl Address of the vault implementation contract for blueprint deployment
    @param _strategy_impl Address of the strategy implementation contract for blueprint deployment
    @param _harvester_impl Address of the harvester implementation contract for blueprint deployment
    @param _treasury Address where platform fees will be collected
    Implementation Contracts:
    - Vault: Manages user deposits/withdrawals and interfaces with strategies
    - Strategy: Handles Convex Finance integration and reward collection
    - Harvester: Processes rewards, swaps tokens, and distributes fees
    """
    ownable.__init__()
    ownable._transfer_ownership(msg.sender)

    VAULT_IMPLEMENTATION = _vault_impl
    STRATEGY_IMPLEMENTATION = _strategy_impl
    HARVESTER_IMPLEMENTATION = _harvester_impl

    self.treasury = _treasury


@external
def set_treasury(_new_treasury: address):
    """
    @notice Set a new treasury address, i.e. address that will receive the platform fees
    @param _new_treasury Treasury address
    """
    ownable._check_owner()
    self.treasury = _new_treasury
    log TreasuryUpdated(treasury=_new_treasury)


@external
def deploy_new_vault(
    _booster_id: uint256,
    _harvest_manager: address,
    _strategy_manager: address,
    _harvester_reward_hook: address,
    _harvester_target_hook: address,
) -> (address, address, address):
    """
    @notice Deploys a new permissioned vault and its associated strategy and harvester contracts
            for a given Convex Booster pool.
    @dev
        - Ensures the selected pool is active via Booster.
        - Vault and strategy token metadata are derived from the underlying asset and pool ID.
        - Hooks for extra reward and target can be set optionally.
    @param _booster_id The Convex Booster id of the pool the vault will autocompound
    @param _harvest_manager Address who will be authorized to execute harvests
    @param _strategy_manager Address who will be authorized to configure the strategy
    @param _harvester_reward_hook Address of extra reward hook for harvester (optional).
    @param _harvester_target_hook Address of target hook for harvester (optional).
    @return vault The deployed vault contract address.
    @return strategy The deployed strategy contract address.
    @return harvester The deployed harvester contract address.
    @custom:reverts
        - If the specified pool is inactive (shut down).
        - If the pool id does not exist in the Booster.
    """

    deployed_harvester: address = create_from_blueprint(HARVESTER_IMPLEMENTATION, self)
    # transaction will revert if id booster is incorrect


    pool_info: (address, address, address, address, address, bool) = staticcall IBooster(
        constants.CONVEX_BOOSTER
    ).poolInfo(_booster_id)


    # ensure pool is not shutdown
    assert pool_info[5] == False

    pool_reward_contract: address = pool_info[3]
    pool_asset: address = pool_info[0]

    # Can be problematic if pool symbol is > 20, however Curve pools LP token's
    # symbol is 10 chars + '-f' suffix.
    pool_asset_symbol: String[20] = staticcall IERC20Detailed(pool_asset).symbol()
    vault_token_name: String[25] = concat("RAAC-", pool_asset_symbol)


    # we use the pool's booster ID as symbol since snekmate limits symbols to 5 chars
    # to avoid URLs in symbols. Some tokens might have similar symbols if Convex ever
    # reaches 100k pools. This is however neither likely in the near future nor a
    # major security risk

    vault_symbol: String[78] = conversion.uint_to_str5(_booster_id)

    deployed_strategy: address = create_from_blueprint(
        STRATEGY_IMPLEMENTATION,
        pool_asset,
        pool_reward_contract,
        deployed_harvester,
        _booster_id,
    )
    deployed_vault: address = create_from_blueprint(
        VAULT_IMPLEMENTATION,
        vault_token_name,
        vault_symbol,
        pool_asset,
        empty(uint256),
        vault_token_name,
        vault_symbol,
        deployed_strategy,
    )


    # Grant roles to managers
    extcall IVault(deployed_vault).grantRole(
        staticcall IVault(deployed_vault).STRATEGY_MANAGER_ROLE(),
        _strategy_manager,
    )
    extcall IVault(deployed_vault).grantRole(
        staticcall IVault(deployed_vault).HARVESTER_ROLE(), _harvest_manager
    )

    # Approve spending on pool/staking contracts
    extcall IStrategy(deployed_strategy).set_approvals()
    extcall IHarvester(deployed_harvester).set_approvals()

    # Link strategy and harvester dependencies
    extcall IStrategy(deployed_strategy).set_vault(deployed_vault)
    extcall IHarvester(deployed_harvester).set_strategy(deployed_strategy)

    # Set hooks if specified
    if _harvester_reward_hook != empty(address):
        extcall IVault(deployed_vault).set_extra_reward_hook(_harvester_reward_hook)
    if _harvester_target_hook != empty(address):
        extcall IVault(deployed_vault).set_target_hook(_harvester_target_hook)

    self.vaults_deployed += 1

    self.vault_registry[self.vaults_deployed] = VaultRecord(
        vault=deployed_vault,
        booster_id=_booster_id,
        strategy=deployed_strategy,
        harvester=deployed_harvester,
        token=pool_asset,
    )

    self.vault_to_id[deployed_vault] = self.vaults_deployed

    log VaultDeployed(
        id=self.vaults_deployed,
        vault=deployed_vault,
        strategy=deployed_strategy,
        harvester=deployed_harvester,
        token=pool_asset,
    )

    return deployed_vault, deployed_strategy, deployed_harvester


@external
def update_harvester(_new_harvester: address):
    vault_id: uint256 = self.vault_to_id[msg.sender]
    assert self.vault_registry[vault_id].vault == msg.sender, "Vault only"
    self.vault_registry[vault_id] = VaultRecord(
        vault=self.vault_registry[vault_id].vault,
        booster_id=self.vault_registry[vault_id].booster_id,
        strategy=self.vault_registry[vault_id].strategy,
        harvester=_new_harvester,
        token=self.vault_registry[vault_id].token,
    )
