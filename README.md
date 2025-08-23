# RAAC Vaults

A modular DeFi yield optimization protocol built on Vyper that autocompounds rewards from Convex Finance positions through various swap mechanisms.

## Overview

The factory allows users to creates ERC4626-compliant vaults that automatically compound CRV and CVX rewards from Convex staking positions back into the underlying LP tokens. The protocol features a modular architecture with pluggable harvesters and hooks to support different trading strategies and MEV protection mechanisms.

### Basic Usage Flow
1. Deploy a factory with your chosen harvester type (Curve, CoW, or Oracle)
2. Create a vault for a specific Convex pool using `factory.deploy_new_vault()`
3. Users deposit LP tokens into the vault and receive vault shares
4. Rewards accumulate automatically from Convex staking
5. Anyone with the Harvester role calls `harvest()` to compound rewards
6. Users can withdraw their LP tokens plus compounded rewards anytime

### Out of audit scope
- snekmate's ownable and access control modules (already audited)
- add_liquidity_ng.vy hook

## Architecture

The protocol consists of five core components that work together to provide automated yield optimization:

### Factory

The **Factory** (`src/factory.vy`) serves as the deployment hub for the entire system.
It uses blueprint contracts to efficiently deploy interconnected vault ecosystems.
The type of vault (curve, oracle, cowswap) the factory deploys depends on the implementations specified in the constructor. A factory is only meant to deploy one specific type of vault.

**Key Features:**
- Deploys vault, strategy, and harvester contracts as a unified system
- Manages vault registry and metadata
- Handles role assignments and contract linking
- Supports upgrading harvester implementations

**Key Functions:**
- `deploy_new_vault()` - Creates a complete vault ecosystem for a Convex pool
- `set_treasury()` - Updates platform fee recipient


### Strategy

The **Strategy** (`src/strategy.vy`) acts as the bridge between vaults and Curve/Convex, managing the actual staking operations and reward collection.
Separating out the strategy also opens the possibility of having a permissioned migration feature.

**Key Features:**
- Handles deposits and withdrawals to/from Convex Booster
- Collects CRV, CVX, and extra rewards from staking contracts
- Forwards rewards to harvester for processing
- Manages platform and caller fee configurations

**Key Functions:**
- `deposit()` - Stakes LP tokens in Convex
- `withdraw()` - Unstakes LP tokens from Convex, but doesn't collect rewards as that will happen during harvesting
- `harvest()` - Collects rewards and triggers harvester processing
- `total_assets()` - Returns total staked balance

### Vault

The **Vault** (`src/raac_vault.vy`, `src/modules/vault.vy`) implements ERC4626 standard for tokenized yield strategies with role-based access control.

**Key Features:**
- ERC4626-compliant deposit/withdrawal interface
- Role-based permissions (Strategy Manager, Harvester)
- Integrates with strategy for yield generation
- Access control for administrative functions

**Roles:**
- **Strategy Manager**: Controls strategy parameters and harvester settings (intended for DAO)
- **Harvester Role**: Can trigger harvest operations (keeper bots or permissionless contracts)

### Harvester

The protocol supports three different harvester implementations, each optimized for different security and MEV protection requirements:

#### Curve Harvester (`src/harvesters/curve_harvester.vy`)
- **Purpose**: Permissioned harvesting with no MEV protection. Harvester can but is not obligated to specify a minimum amount of output tokens.
- **Security**: Minimal slippage protection as users can set `min_amount_out` to zero. Curve pools are somewhat more resistant to sandwiching but this type of vault is nonetheless meant for permissioned harvests where a trusted keeper(s) will compute the appropriate minimum amount of input token off-chain.


#### CoW Harvester (`src/harvesters/cow_harvester.vy`)
- **Purpose**: Uses CoWSwap to sell rewards, ensuring better price execution via competitive auctions
- **Security**: MEV protection through CoW Swap's batch auction mechanism. Generally finds optimum prices as searchers don't typically collude. Although the CoW vaults are meant to be permissioned, they can potentially be made permissionless. For instance, Curve has been using CoW to handle the sales of its fees to crvUSD for several months in a permissionless manner and with no minimum amount specified for the trades. The lack of searcher collusion and the competitive nature of the price discovery process on CoWswap have (so far) offered superior prices.
- **Use Case**: Balance between security and decentralization (Curve uses similar approach for fee burning)

#### Oracle Harvester (`src/harvesters/oracle_harvester.vy`)
- **Purpose**: Fully permissionless with oracle-based MEV protection
- **Security**: Uses Curve pool oracles and Chainlink (for crvUSD) to validate swap prices. This allows for permissionless harvests, but is much more gas intensive. In the basic implementation, we use pool oracle for tokens swaps. For the final liquidity addition prior to autocompounding (meant for 2-asset stableswap NG pools) we use the formula `min(usd_prices) * virtual_price` as an oracle for the LP token price where prices are obtained via Chainlink (for crvUSD) and the pool's internal oracle. Relying on pool oracles may also temporarily prevent harvesting in times of high volatility when oracles are lagging compared to spot price. The acceptable level of slippage can be adjusted by the harvest manager.

### Hooks

**Hooks** provide extensible functionality for processing rewards and adding liquidity:

#### Add Liquidity Hook (`src/hooks/add_liquidity.vy`)
- Designed as a post-hook - a final step to get the strategy's target token (usually a Curve LP token)
- Handles one-sided liquidity addition to Curve NG pools
- Converts reward tokens into LP tokens for compounding
- Supports up to 8-coin pools with flexible token indexing

#### Add Liquidity Oracle Hook (`src/hooks/add_liquidity_oracle.vy`)
- Same as above but using oracles to prevent slippage

#### Handle Extra Rewards Hook (`src/hooks/handle_extra_rewards.vy`)
- Processes additional reward tokens beyond CRV/CVX
- Can be used to unwrap LP tokens, ERC4626 wrapped tokens and other exotic tokens

The hooks provided are meant as generic examples and may require further adaptation depending on the type of pools and it's rewards.

## Fee Mechanisms

The protocol implements a dual-fee structure to sustain operations and incentivize harvest calls:

### Platform Fee
- **Purpose**: Revenue for protocol treasury and development
- **Default Rate**: 20% (2000 basis points) of harvested crvUSD
- **Maximum**: Set to 30% (3000 basis points)
- **Collection**: Taken as a percentage of the final crvUSD amount after rewards are swapped
- **Distribution**: Sent directly to the treasury address in crvUSD
- **Management**: Configurable by Strategy Manager role

### Caller Fee
- **Purpose**: Compensate harvesters for gas costs and provide harvest incentives
- **Default Rate**: 1% (100 basis points) of harvested crvUSD
- **Maximum**: Set to 10% (1000 basis points)
- **Collection**: Taken as a percentage of the final crvUSD amount after rewards are swapped
- **Recipient**: Address that calls the harvest function (keeper bots, EOAs, etc.)
- **Distribution**: Sent directly to the caller in crvUSD
- **Management**: Configurable by Strategy Manager role - however may need to be handled differently as the caller fee should be able to be adjusted to optimize harvest frequency based on expected yield and gas prices.


## Management Roles

### Strategy Manager
- **Intended Role**: DAO governance
- **Permissions**: Configure strategy parameters, fees, and harvester settings

### Harvester Manager
- **Flexible Implementation**: Single keeper bot, whitelist contract, or permissionless proxy
- **Permissions**: Trigger harvest operations
- **Options**:
  - Single trusted keeper for efficiency
  - Whitelist contract for multiple authorized keepers
  - Permissionless contract for fully decentralized harvesting

## Development

The project uses Moccasin for development and testing:

```bash
# Install dependencies
uv venv
source .venv/bin/activate
uv pip install .
uv run moccasin install
```

The project expect an .env file with the following values:

```
ETHERSCAN_TOKEN=
MAINNET_RPC_URL=
```

## License

MIT License - see individual contract files for details.
