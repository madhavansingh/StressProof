// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {Deploy} from "../script/Deploy.s.sol";

/// @notice Tests for script/Deploy.s.sol: configuration, role separation (C-15), parameter checks,
/// deployment order and the deployments-file metadata (implementationplan.md §8.7, §12.6).
contract DeployTest is Test {
    /// stressproof_core.market_id("aave-v3-eth-weth-stable"), computed with the Python core library.
    bytes32 internal constant CORE_MARKET_ID = 0x2701f07d2eb0de529ccb283ac9cd1ebb8ed772916b7db0822335d9bcdabbc026;
    string internal constant MARKET_ID_STRING = "aave-v3-eth-weth-stable";
    string internal constant GIT_SHA = "0123456789abcdef0123456789abcdef01234567";
    uint256 internal constant FIXTURE_R = 200_000_000_001;

    Deploy internal script;

    address internal deployer;
    uint256 internal deployerKey;
    address internal attester;
    uint256 internal attesterKey;
    address internal malicious;
    uint256 internal maliciousKey;
    address internal watcher;
    uint256 internal watcherKey;
    address internal resolver;
    uint256 internal resolverKey;

    function setUp() public {
        script = new Deploy();
        (deployer, deployerKey) = makeAddrAndKey("deployer");
        (attester, attesterKey) = makeAddrAndKey("attester");
        (malicious, maliciousKey) = makeAddrAndKey("malicious");
        (watcher, watcherKey) = makeAddrAndKey("watcher");
        (resolver, resolverKey) = makeAddrAndKey("resolver");
    }

    /// The MVP values from .env.example, with fixture thresholds LTV = R/2, PAUSE = 2R (plan §12.5).
    function _validConfig() internal view returns (Deploy.Config memory cfg) {
        cfg.deployerKey = deployerKey;
        cfg.roles = Deploy.Roles(deployer, attester, malicious, watcher, resolver);
        cfg.bond = 0.01 ether;
        cfg.challengeWindow = 120;
        cfg.resolutionWindow = 300;
        cfg.toleranceBps = 0;
        cfg.marketIdString = MARKET_ID_STRING;
        cfg.pauseThreshold = 2 * FIXTURE_R;
        cfg.ltvThreshold = FIXTURE_R / 2;
        cfg.reducedLtvBps = 5000;
        cfg.defaultMaxLtvBps = 8000;
        cfg.gitCommit = GIT_SHA;
    }

    // ============================================================ deployment

    function test_runWith_deploysInDocumentedOrder() public {
        uint256 nonce = vm.getNonce(deployer);
        Deploy.Deployment memory d = script.runWith(_validConfig());

        assertEq(address(d.registry), computeCreateAddress(deployer, nonce), "registry first");
        assertEq(address(d.vault), computeCreateAddress(deployer, nonce + 1), "vault second");
        assertEq(address(d.market), computeCreateAddress(deployer, nonce + 2), "market third");
        assertEq(vm.getNonce(deployer), nonce + 3, "exactly three deployments from the deployer");
    }

    function test_runWith_wiresConfigIntoContracts() public {
        Deploy.Config memory cfg = _validConfig();
        Deploy.Deployment memory d = script.runWith(cfg);

        assertEq(d.registry.BOND(), cfg.bond);
        assertEq(d.registry.CHALLENGE_WINDOW(), cfg.challengeWindow);
        assertEq(d.registry.RESOLUTION_WINDOW(), cfg.resolutionWindow);
        assertEq(d.registry.TOLERANCE_BPS(), 0);
        assertEq(d.registry.resolver(), resolver);

        assertEq(address(d.vault.registry()), address(d.registry));
        assertEq(d.vault.MARKET_ID(), CORE_MARKET_ID);
        assertEq(d.vault.owner(), deployer, "deployer owns the vault");
        assertEq(d.vault.PAUSE_THRESHOLD(), cfg.pauseThreshold);
        assertEq(d.vault.LTV_THRESHOLD(), cfg.ltvThreshold);
        assertEq(d.vault.REDUCED_LTV_BPS(), cfg.reducedLtvBps);
        assertEq(d.vault.DEFAULT_MAX_LTV_BPS(), cfg.defaultMaxLtvBps);
        assertEq(d.vault.maxLtvBps(), cfg.defaultMaxLtvBps);
        assertFalse(d.vault.borrowPaused());

        assertEq(address(d.market.vault()), address(d.vault));
    }

    function test_marketId_matchesCoreLibrary() public {
        assertEq(script.marketIdOf(MARKET_ID_STRING), CORE_MARKET_ID);
        assertEq(script.marketIdOf(MARKET_ID_STRING), keccak256(bytes(MARKET_ID_STRING)));
        Deploy.Deployment memory d = script.runWith(_validConfig());
        assertEq(d.marketId, CORE_MARKET_ID);
        // The value hand-written into deployments/*.json before this script existed was wrong.
        assertTrue(d.marketId != 0x40d51381e4b3e8a71bbbf288e285817d4567c9c0f99b2eb8c15682fa08d3c7c2);
    }

    function test_runWith_acceptsBaseSepolia() public {
        vm.chainId(84532);
        Deploy.Deployment memory d = script.runWith(_validConfig());
        assertGt(address(d.registry).code.length, 0);
    }

    // ===================================================== deployments file
    // The deployments file is written by scripts/deploy.sh from confirmed receipts
    // (tested in scripts/tests). These tests pin down that forge itself never writes it.

    /// Running the script leaves the committed deployments file byte-identical.
    function test_runWith_writesNoDeploymentsFile() public {
        string memory path = "../deployments/31337.json";
        bytes32 before = keccak256(bytes(vm.readFile(path)));
        script.runWith(_validConfig());
        assertEq(keccak256(bytes(vm.readFile(path))), before);
    }

    /// foundry.toml gives forge read-only access to deployments/, so even a script that tried
    /// to write there during simulation would fail instead of overwriting the file.
    function test_forgeCannotWriteDeploymentsFolder() public {
        string[2] memory paths = ["../deployments/31337.json", "../deployments/should-not-exist.json"];
        for (uint256 i; i < paths.length; ++i) {
            try vm.writeFile(paths[i], "overwritten") {
                revert("forge was able to write to deployments/");
            } catch {}
        }
        assertFalse(vm.exists("../deployments/should-not-exist.json"));
    }

    // ============================================================ validation

    function test_validate_acceptsValidConfig() public view {
        script.validate(_validConfig());
    }

    function test_validate_rejectsUnsupportedChains() public {
        uint256[4] memory chains = [uint256(1), 8453, 11155111, 31338];
        for (uint256 i; i < chains.length; ++i) {
            vm.chainId(chains[i]);
            vm.expectRevert(abi.encodeWithSelector(Deploy.UnsupportedChain.selector, chains[i]));
            script.validate(_validConfig());
        }
    }

    /// C-15: every pair of the five roles must differ.
    function test_validate_rejectsEveryDuplicateRolePair() public {
        string[5] memory names = [string("DEPLOYER"), "ATTESTER", "MALICIOUS", "WATCHER", "RESOLVER"];
        uint256 checked;
        for (uint256 i = 1; i < 5; ++i) {
            for (uint256 j; j < i; ++j) {
                Deploy.Config memory cfg = _validConfig();
                address dup = _roleAt(cfg, j);
                _setRole(cfg, i, dup);
                vm.expectRevert(abi.encodeWithSelector(Deploy.DuplicateRole.selector, names[j], names[i]));
                script.validate(cfg);
                ++checked;
            }
        }
        assertEq(checked, 10);
    }

    // ============================================ public dev accounts (testnet)

    /// The mnemonic behind Anvil's and Hardhat's default accounts; its keys are public.
    string internal constant DEV_MNEMONIC = "test test test test test test test test test test test junk";

    function _devKey(uint32 index) internal pure returns (uint256) {
        return vm.deriveKey(DEV_MNEMONIC, index);
    }

    function test_validate_rejectsPublicDevAccountForEveryRoleOnBaseSepolia() public {
        vm.chainId(84532);
        string[5] memory names = ["DEPLOYER", "ATTESTER", "MALICIOUS", "WATCHER", "RESOLVER"];
        for (uint256 i; i < 5; ++i) {
            Deploy.Config memory cfg = _validConfig();
            uint256 key = _devKey(uint32(i));
            address dev = vm.addr(key);
            if (i == 0) {
                cfg.deployerKey = key;
                cfg.roles.deployer = dev;
            } else if (i == 1) {
                cfg.roles.attester = dev;
            } else if (i == 2) {
                cfg.roles.malicious = dev;
            } else if (i == 3) {
                cfg.roles.watcher = dev;
            } else {
                cfg.roles.resolver = dev;
            }
            vm.expectRevert(abi.encodeWithSelector(Deploy.PublicDevAccount.selector, names[i], dev));
            script.validate(cfg);
        }
    }

    function test_validate_rejectsLaterDevAccountsOnBaseSepolia() public {
        vm.chainId(84532);
        Deploy.Config memory cfg = _validConfig();
        address hardhatLast = vm.addr(_devKey(19)); // Hardhat's 20th default account
        cfg.roles.watcher = hardhatLast;
        vm.expectRevert(abi.encodeWithSelector(Deploy.PublicDevAccount.selector, "WATCHER", hardhatLast));
        script.validate(cfg);
    }

    function test_validate_allowsPublicDevAccountsOnLocalAnvil() public view {
        // chain 31337 (the default in tests): local development keeps using the Anvil accounts.
        Deploy.Config memory cfg = _validConfig();
        cfg.deployerKey = _devKey(0);
        cfg.roles = Deploy.Roles(vm.addr(_devKey(0)), vm.addr(_devKey(2)), vm.addr(_devKey(4)), vm.addr(_devKey(3)), vm.addr(_devKey(1)));
        script.validate(cfg);
    }

    function test_validate_rejectsZeroRoleAddress() public {
        string[4] memory names = ["ATTESTER", "MALICIOUS", "WATCHER", "RESOLVER"];
        for (uint256 i = 1; i < 5; ++i) {
            Deploy.Config memory cfg = _validConfig();
            _setRole(cfg, i, address(0));
            vm.expectRevert(abi.encodeWithSelector(Deploy.ZeroRoleAddress.selector, names[i - 1]));
            script.validate(cfg);
        }
    }

    function test_validate_rejectsBadDeployerKey() public {
        Deploy.Config memory cfg = _validConfig();
        cfg.deployerKey = 0;
        vm.expectRevert(abi.encodeWithSelector(Deploy.ZeroParameter.selector, "DEPLOYER_PK"));
        script.validate(cfg);

        cfg = _validConfig();
        cfg.deployerKey = attesterKey; // key does not belong to roles.deployer
        vm.expectRevert(Deploy.DeployerKeyMismatch.selector);
        script.validate(cfg);
    }

    function test_validate_rejectsNonZeroTolerance() public {
        Deploy.Config memory cfg = _validConfig();
        cfg.toleranceBps = 1;
        vm.expectRevert(abi.encodeWithSelector(Deploy.ToleranceNotZero.selector, 1));
        script.validate(cfg);
    }

    function test_validate_rejectsBadRegistryParams() public {
        Deploy.Config memory cfg = _validConfig();
        cfg.bond = 0;
        vm.expectRevert(abi.encodeWithSelector(Deploy.ZeroParameter.selector, "BOND_WEI"));
        script.validate(cfg);

        cfg = _validConfig();
        cfg.challengeWindow = 0;
        vm.expectRevert(abi.encodeWithSelector(Deploy.ZeroParameter.selector, "CHALLENGE_WINDOW_SEC"));
        script.validate(cfg);

        cfg = _validConfig();
        cfg.resolutionWindow = uint256(type(uint64).max) + 1;
        vm.expectRevert(
            abi.encodeWithSelector(Deploy.ValueOutOfRange.selector, "RESOLUTION_WINDOW_SEC", cfg.resolutionWindow)
        );
        script.validate(cfg);

        cfg = _validConfig();
        cfg.marketIdString = "";
        vm.expectRevert(Deploy.EmptyMarketId.selector);
        script.validate(cfg);
    }

    function test_validate_rejectsBadThresholds() public {
        Deploy.Config memory cfg = _validConfig();
        cfg.ltvThreshold = 0;
        vm.expectRevert(abi.encodeWithSelector(Deploy.InvalidThresholds.selector, 0, cfg.pauseThreshold));
        script.validate(cfg);

        cfg = _validConfig();
        cfg.pauseThreshold = cfg.ltvThreshold - 1;
        vm.expectRevert(
            abi.encodeWithSelector(Deploy.InvalidThresholds.selector, cfg.ltvThreshold, cfg.pauseThreshold)
        );
        script.validate(cfg);

        cfg = _validConfig();
        cfg.pauseThreshold = cfg.ltvThreshold; // boundary: equal is allowed
        script.validate(cfg);
    }

    function test_validate_rejectsBadLtvBps() public {
        uint256[2][3] memory bad = [[uint256(8000), 8000], [uint256(9000), 8000], [uint256(5000), 10_001]];
        for (uint256 i; i < bad.length; ++i) {
            Deploy.Config memory cfg = _validConfig();
            cfg.reducedLtvBps = bad[i][0];
            cfg.defaultMaxLtvBps = bad[i][1];
            vm.expectRevert(abi.encodeWithSelector(Deploy.InvalidLtvBps.selector, bad[i][0], bad[i][1]));
            script.validate(cfg);
        }
        Deploy.Config memory edge = _validConfig();
        edge.defaultMaxLtvBps = 10_000; // boundary: 100% is allowed
        script.validate(edge);
    }

    function test_validate_rejectsBadGitCommit() public {
        string[4] memory bad = [
            string(""),
            "502831a", // short sha
            "0123456789ABCDEF0123456789abcdef01234567", // uppercase
            "0123456789abcdef0123456789abcdef0123456g" // not hex
        ];
        for (uint256 i; i < bad.length; ++i) {
            Deploy.Config memory cfg = _validConfig();
            cfg.gitCommit = bad[i];
            vm.expectRevert(abi.encodeWithSelector(Deploy.InvalidGitCommit.selector, bad[i]));
            script.validate(cfg);
        }
    }

    // ========================================================= env loading

    /// All env-dependent checks live in this one test: forge runs tests in parallel and
    /// environment variables are shared by the whole process.
    function test_loadConfig_readsEnvironment() public {
        _setValidEnv();
        Deploy.Config memory cfg = script.loadConfig();
        assertEq(cfg.deployerKey, deployerKey);
        assertEq(cfg.roles.deployer, deployer);
        assertEq(cfg.roles.attester, attester);
        assertEq(cfg.roles.malicious, malicious);
        assertEq(cfg.roles.watcher, watcher);
        assertEq(cfg.roles.resolver, resolver);
        assertEq(cfg.bond, 0.01 ether);
        assertEq(cfg.pauseThreshold, 2 * FIXTURE_R);
        assertEq(cfg.ltvThreshold, FIXTURE_R / 2);
        assertEq(cfg.gitCommit, GIT_SHA);
        script.validate(cfg);

        // <ROLE>_ADDRESS takes precedence over <ROLE>_PK; an empty value falls back to the key.
        address separateResolver = makeAddr("resolver-on-another-machine");
        vm.setEnv("RESOLVER_ADDRESS", vm.toString(separateResolver));
        assertEq(script.loadConfig().roles.resolver, separateResolver);
        vm.setEnv("RESOLVER_ADDRESS", "");
        assertEq(script.loadConfig().roles.resolver, resolver);

        // The full entry point works from the environment.
        Deploy.Deployment memory d = script.run();
        assertEq(d.registry.resolver(), resolver);

        // Thresholds left empty, as in .env.example before the sweep, stop the deploy.
        vm.setEnv("PAUSE_THRESHOLD_USD8", "");
        vm.expectRevert();
        script.loadConfig();
    }

    // ============================================================== helpers

    function _setValidEnv() internal {
        vm.setEnv("DEPLOYER_PK", vm.toString(bytes32(deployerKey))); // 0x-hex, as in a real .env
        vm.setEnv("ATTESTER_PK", vm.toString(attesterKey)); // decimal also parses
        vm.setEnv("MALICIOUS_PK", vm.toString(bytes32(maliciousKey)));
        vm.setEnv("WATCHER_PK", vm.toString(bytes32(watcherKey)));
        vm.setEnv("RESOLVER_PK", vm.toString(bytes32(resolverKey)));
        vm.setEnv("RESOLVER_ADDRESS", "");
        vm.setEnv("BOND_WEI", "10000000000000000");
        vm.setEnv("CHALLENGE_WINDOW_SEC", "120");
        vm.setEnv("RESOLUTION_WINDOW_SEC", "300");
        vm.setEnv("TOLERANCE_BPS", "0");
        vm.setEnv("MARKET_ID_STRING", MARKET_ID_STRING);
        vm.setEnv("PAUSE_THRESHOLD_USD8", vm.toString(2 * FIXTURE_R));
        vm.setEnv("LTV_THRESHOLD_USD8", vm.toString(FIXTURE_R / 2));
        vm.setEnv("REDUCED_LTV_BPS", "5000");
        vm.setEnv("DEFAULT_MAX_LTV_BPS", "8000");
        vm.setEnv("GIT_COMMIT", GIT_SHA);
    }

    function _roleAt(Deploy.Config memory cfg, uint256 i) internal pure returns (address) {
        Deploy.Roles memory r = cfg.roles;
        return [r.deployer, r.attester, r.malicious, r.watcher, r.resolver][i];
    }

    /// Index 0 is the deployer, which must also match the key, so only 1..4 are replaced here.
    function _setRole(Deploy.Config memory cfg, uint256 i, address value) internal pure {
        if (i == 1) cfg.roles.attester = value;
        else if (i == 2) cfg.roles.malicious = value;
        else if (i == 3) cfg.roles.watcher = value;
        else if (i == 4) cfg.roles.resolver = value;
        else revert("deployer cannot be replaced without its key");
    }
}
