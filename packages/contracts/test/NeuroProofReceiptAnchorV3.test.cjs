"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");

const { ethers } = require("ethers");
const solc = require("solc");
const hre = require("hardhat");

const CONTRACT_NAME = "NeuroProofReceiptAnchorV3";

const SOURCE_FILE = path.join(
  __dirname,
  "../contracts/NeuroProofReceiptAnchorV3.sol"
);

const V3_DOMAIN =
  "cerebrachain-v3:development-synthetic-proof-receipt-anchor:v1";

const V2_DOMAIN =
  "cerebrachain-v2:proof-receipt-anchor:v1";

function compileV3() {
  const source = fs.readFileSync(SOURCE_FILE, "utf8");

  const filename = "NeuroProofReceiptAnchorV3.sol";

  const input = {
    language: "Solidity",
    sources: {
      [filename]: { content: source }
    },
    settings: {
      optimizer: {
        enabled: true,
        runs: 200
      },
      outputSelection: {
        "*": {
          "*": ["abi", "evm.bytecode.object"]
        }
      }
    }
  };

  const result = JSON.parse(
    solc.compile(JSON.stringify(input))
  );

  const errors = (result.errors || []).filter(
    item => item.severity === "error"
  );

  assert.equal(
    errors.length,
    0,
    errors.map(item => item.formattedMessage).join("\n")
  );

  const contract =
    result.contracts?.[filename]?.[CONTRACT_NAME];

  assert.ok(contract, "V3 compiled contract missing");
  assert.ok(contract.evm.bytecode.object);

  return contract;
}

const compiled = compileV3();

async function fixture() {
  assert.equal(
    hre.network.name,
    "hardhat",
    "Tests must use only the in-memory Hardhat network"
  );

  const provider = new ethers.BrowserProvider(
    hre.network.provider
  );

  const network = await provider.getNetwork();

  assert.equal(
    network.chainId,
    31337n,
    "Unexpected test network"
  );

  const owner = await provider.getSigner(0);
  const anchorer = await provider.getSigner(1);
  const outsider = await provider.getSigner(2);

  const factory = new ethers.ContractFactory(
    compiled.abi,
    compiled.evm.bytecode.object,
    owner
  );

  const contract = await factory.deploy(
    await anchorer.getAddress()
  );

  await contract.waitForDeployment();

  return {
    contract,
    owner,
    anchorer,
    outsider
  };
}

function commitment(label) {
  return ethers.keccak256(
    ethers.toUtf8Bytes(`neuroproof-v3-test:${label}`)
  );
}

function syntheticReceipt(suffix) {
  return {
    federationRoundCommitment:
      commitment(`round:${suffix}`),

    modelVersionCommitment:
      commitment(`model:${suffix}`),

    hospitalUpdateCommitment:
      commitment(`update:${suffix}`),

    proofArtifactSha256:
      commitment(`synthetic-proof:${suffix}`),

    verificationKeyId:
      commitment(`development-key:${suffix}`)
  };
}

test("V3 classification is development-only", async () => {
  const { contract } = await fixture();

  assert.equal(
    await contract.ATTESTATION_CLASSIFICATION(),
    "development_synthetic_offchain_verified"
  );

  assert.equal(
    await contract.PRODUCTION_ELIGIBLE(),
    false
  );

  assert.equal(
    await contract.ONCHAIN_GROTH16_VERIFIED(),
    false
  );

  assert.equal(
    await contract.RECEIPT_DOMAIN(),
    ethers.keccak256(ethers.toUtf8Bytes(V3_DOMAIN))
  );
});

test("Unauthorized accounts cannot anchor receipts", async () => {
  const { contract, owner, outsider } = await fixture();

  const payload = syntheticReceipt("unauthorized");

  await assert.rejects(async () => {
    const tx = await contract
      .connect(outsider)
      .anchorReceipt(payload);

    await tx.wait();
  });

  await assert.rejects(async () => {
    const tx = await contract
      .connect(owner)
      .anchorReceipt(payload);

    await tx.wait();
  });

  const id = await contract.computeReceiptId(payload);

  assert.equal(
    await contract.receiptExists(id),
    false
  );
});

test("Authorized anchorer records immutable receipt", async () => {
  const { contract, anchorer } = await fixture();

  const payload = syntheticReceipt("accepted");

  const expectedId =
    await contract.computeReceiptId(payload);

  const tx = await contract
    .connect(anchorer)
    .anchorReceipt(payload);

  const transactionReceipt = await tx.wait();

  assert.equal(transactionReceipt.status, 1);

  assert.equal(
    await contract.receiptExists(expectedId),
    true
  );

  const stored = await contract.getReceipt(expectedId);

  assert.equal(
    stored.federationRoundCommitment,
    payload.federationRoundCommitment
  );

  assert.equal(
    stored.modelVersionCommitment,
    payload.modelVersionCommitment
  );

  assert.equal(
    stored.hospitalUpdateCommitment,
    payload.hospitalUpdateCommitment
  );

  assert.equal(
    stored.proofArtifactSha256,
    payload.proofArtifactSha256
  );

  assert.equal(
    stored.verificationKeyId,
    payload.verificationKeyId
  );

  assert.equal(
    stored.attestationStatus,
    0n
  );

  assert.equal(
    stored.attestedBy,
    await anchorer.getAddress()
  );

  const events = transactionReceipt.logs
    .map(log => {
      try {
        return contract.interface.parseLog(log);
      } catch {
        return null;
      }
    })
    .filter(Boolean);

  const anchoredEvent = events.find(
    event => event.name === "ReceiptAnchored"
  );

  assert.ok(anchoredEvent);
  assert.equal(
    anchoredEvent.args.receiptId,
    expectedId
  );
});

test("Duplicate and zero commitments are rejected", async () => {
  const { contract, anchorer } = await fixture();

  const payload = syntheticReceipt("duplicate");

  const first = await contract
    .connect(anchorer)
    .anchorReceipt(payload);

  await first.wait();

  await assert.rejects(async () => {
    const duplicate = await contract
      .connect(anchorer)
      .anchorReceipt(payload);

    await duplicate.wait();
  });

  const invalid = {
    ...syntheticReceipt("invalid"),
    proofArtifactSha256: ethers.ZeroHash
  };

  await assert.rejects(async () => {
    const tx = await contract
      .connect(anchorer)
      .anchorReceipt(invalid);

    await tx.wait();
  });

  assert.equal(
    await contract.receiptExists(
      await contract.computeReceiptId(invalid)
    ),
    false
  );
});

test("Owner controls anchoring authorization", async () => {
  const {
    contract,
    owner,
    anchorer,
    outsider
  } = await fixture();

  const anchorerAddress =
    await anchorer.getAddress();

  assert.equal(
    await contract.isAnchoringAccount(anchorerAddress),
    true
  );

  const revokeTx = await contract
    .connect(owner)
    .setAnchoringAccount(anchorerAddress, false);

  await revokeTx.wait();

  assert.equal(
    await contract.isAnchoringAccount(anchorerAddress),
    false
  );

  await assert.rejects(async () => {
    const tx = await contract
      .connect(anchorer)
      .anchorReceipt(syntheticReceipt("revoked"));

    await tx.wait();
  });

  const newOwner = await outsider.getAddress();

  const transferTx = await contract
    .connect(owner)
    .transferOwnership(newOwner);

  await transferTx.wait();

  assert.equal(
    await contract.owner(),
    newOwner
  );

  await assert.rejects(async () => {
    const tx = await contract
      .connect(owner)
      .setAnchoringAccount(anchorerAddress, true);

    await tx.wait();
  });
});

test("V3 receipt IDs are domain-separated from V2", async () => {
  const { contract } = await fixture();

  const payload = syntheticReceipt("domain");

  const v3Id =
    await contract.computeReceiptId(payload);

  const v2DomainHash = ethers.keccak256(
    ethers.toUtf8Bytes(V2_DOMAIN)
  );

  const encoded = ethers.AbiCoder
    .defaultAbiCoder()
    .encode(
      [
        "bytes32",
        "bytes32",
        "bytes32",
        "bytes32",
        "bytes32",
        "bytes32"
      ],
      [
        v2DomainHash,
        payload.federationRoundCommitment,
        payload.modelVersionCommitment,
        payload.hospitalUpdateCommitment,
        payload.proofArtifactSha256,
        payload.verificationKeyId
      ]
    );

  const v2Id = ethers.keccak256(encoded);

  assert.notEqual(
    v3Id,
    v2Id,
    "V3 receipt ID must differ from V2"
  );
});
