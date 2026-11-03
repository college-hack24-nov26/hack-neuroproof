"use strict";

const assert = require("node:assert/strict");
const net = require("node:net");
const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { after, before, beforeEach, test } = require("node:test");
const { ethers } = require("ethers");

const { compileAnchor } = require("../scripts/compile.cjs");

const packageRoot = path.resolve(__dirname, "..");
let nodeProcess;
let provider;
let contract;
let owner;
let authorizedAnchorer;
let unauthorized;
let compiled;

function commitment(label) {
  return ethers.keccak256(ethers.toUtf8Bytes(`synthetic-step-163:${label}`));
}

function syntheticReceipt(suffix = "one") {
  return {
    federationRoundCommitment: commitment(`round:${suffix}`),
    modelVersionCommitment: commitment(`model:${suffix}`),
    hospitalUpdateCommitment: commitment(`update:${suffix}`),
    proofArtifactSha256: commitment(`proof:${suffix}`),
    verificationKeyId: commitment(`verification-key:${suffix}`),
  };
}

async function unusedLocalPort() {
  const server = net.createServer();
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const { port } = server.address();
  await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  return port;
}

function pause(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function waitForRpc(url) {
  for (let attempt = 0; attempt < 80; attempt += 1) {
    try {
      const candidate = new ethers.JsonRpcProvider(
        url,
        { chainId: 31337, name: "hardhat" },
        { staticNetwork: true },
      );
      if (await candidate.send("eth_chainId", []) === "0x7a69") {
        return candidate;
      }
    } catch {
      // The ephemeral node is still starting. Do not print its default test accounts.
    }
    await pause(125);
  }
  throw new Error("Ephemeral isolated Hardhat JSON-RPC node did not become ready.");
}

function receiptValues(receipt) {
  return {
    federationRoundCommitment: receipt.federationRoundCommitment,
    modelVersionCommitment: receipt.modelVersionCommitment,
    hospitalUpdateCommitment: receipt.hospitalUpdateCommitment,
    proofArtifactSha256: receipt.proofArtifactSha256,
    verificationKeyId: receipt.verificationKeyId,
    attestationStatus: receipt.attestationStatus,
    anchoredAt: receipt.anchoredAt,
    anchoredBlock: receipt.anchoredBlock,
    attestedBy: receipt.attestedBy,
  };
}

function configuredHardhatBinary() {
  const localBinary = path.join(packageRoot, "node_modules", ".bin", "hardhat");
  const binary = process.env.HARDHAT_BIN || localBinary;
  if (!fs.existsSync(binary)) {
    throw new Error("Hardhat is not installed for packages/contracts. Run npm ci before testing.");
  }
  return binary;
}

async function deployFreshAnchor() {
  const factory = new ethers.ContractFactory(compiled.abi, compiled.bytecode, owner);
  const deployed = await factory.deploy(await authorizedAnchorer.getAddress());
  await deployed.waitForDeployment();
  return deployed;
}

function receiptAnchoredEvent(transactionReceipt) {
  for (const log of transactionReceipt.logs) {
    try {
      const parsed = contract.interface.parseLog(log);
      if (parsed?.name === "ReceiptAnchored") return parsed;
    } catch {
      // Ignore logs that do not belong to this contract ABI.
    }
  }
  return undefined;
}

before(async () => {
  compiled = compileAnchor();
  const port = await unusedLocalPort();
  const url = `http://127.0.0.1:${port}`;
  nodeProcess = spawn(
    configuredHardhatBinary(),
    ["node", "--hostname", "127.0.0.1", "--port", String(port)],
    { cwd: packageRoot, stdio: ["ignore", "ignore", "ignore"] },
  );
  provider = await waitForRpc(url);
  owner = await provider.getSigner(0);
  authorizedAnchorer = await provider.getSigner(1);
  unauthorized = await provider.getSigner(2);
});

after(async () => {
  if (!nodeProcess || nodeProcess.exitCode !== null) return;
  const exited = new Promise((resolve) => nodeProcess.once("exit", resolve));
  nodeProcess.kill("SIGTERM");
  await Promise.race([exited, pause(3_000)]);
  if (nodeProcess.exitCode === null) {
    nodeProcess.kill("SIGKILL");
    await new Promise((resolve) => nodeProcess.once("exit", resolve));
  }
});

beforeEach(async () => {
  contract = await deployFreshAnchor();
});

test("authorized anchoring stores deterministic immutable metadata and emits the receipt event", async () => {
  const input = syntheticReceipt();
  const expectedReceiptId = await contract.computeReceiptId(input);

  const transaction = await contract.connect(authorizedAnchorer).anchorReceipt(input);
  const receipt = await transaction.wait();
  const anchoredEvent = receiptAnchoredEvent(receipt);
  const stored = await contract.getReceipt(expectedReceiptId);

  assert.equal(await contract.receiptExists(expectedReceiptId), true);
  assert.equal(anchoredEvent.args.receiptId, expectedReceiptId);
  assert.equal(anchoredEvent.args.federationRoundCommitment, input.federationRoundCommitment);
  assert.equal(anchoredEvent.args.hospitalUpdateCommitment, input.hospitalUpdateCommitment);
  assert.equal(anchoredEvent.args.proofArtifactSha256, input.proofArtifactSha256);
  assert.equal(stored.federationRoundCommitment, input.federationRoundCommitment);
  assert.equal(stored.modelVersionCommitment, input.modelVersionCommitment);
  assert.equal(stored.hospitalUpdateCommitment, input.hospitalUpdateCommitment);
  assert.equal(stored.proofArtifactSha256, input.proofArtifactSha256);
  assert.equal(stored.verificationKeyId, input.verificationKeyId);
  assert.equal(stored.attestationStatus, 0n);
  assert.equal(stored.attestedBy, await authorizedAnchorer.getAddress());
  assert.ok(stored.anchoredAt > 0n);
  assert.ok(stored.anchoredBlock > 0n);
});

test("unauthorized accounts cannot anchor a receipt", async () => {
  await assert.rejects(contract.connect(unauthorized).anchorReceipt(syntheticReceipt()));
});

test("a duplicate receipt fails and the original receipt remains immutable", async () => {
  const input = syntheticReceipt();
  const receiptId = await contract.computeReceiptId(input);
  await (await contract.connect(authorizedAnchorer).anchorReceipt(input)).wait();
  const first = await contract.getReceipt(receiptId);

  await assert.rejects(contract.connect(authorizedAnchorer).anchorReceipt(input));

  const afterDuplicate = await contract.getReceipt(receiptId);
  assert.deepEqual(receiptValues(afterDuplicate), receiptValues(first));
});

test("zero commitments and unknown receipt identifiers are rejected", async () => {
  const input = syntheticReceipt();
  for (const field of Object.keys(input)) {
    await assert.rejects(
      contract.connect(authorizedAnchorer).anchorReceipt({ ...input, [field]: ethers.ZeroHash }),
    );
  }
  await assert.rejects(contract.getReceipt(ethers.ZeroHash));
});

test("authorization changes and ownership transfer are explicit and enforced", async () => {
  const newlyAuthorized = await provider.getSigner(3);
  const newOwner = await provider.getSigner(4);

  await assert.rejects(contract.connect(unauthorized).setAnchoringAccount(await newlyAuthorized.getAddress(), true));
  await (await contract.setAnchoringAccount(await newlyAuthorized.getAddress(), true)).wait();
  await (await contract.connect(newlyAuthorized).anchorReceipt(syntheticReceipt("newly-authorized"))).wait();

  await (await contract.setAnchoringAccount(await newlyAuthorized.getAddress(), false)).wait();
  await assert.rejects(contract.connect(newlyAuthorized).anchorReceipt(syntheticReceipt("revoked")));

  await (await contract.transferOwnership(await newOwner.getAddress())).wait();
  await assert.rejects(contract.setAnchoringAccount(await newlyAuthorized.getAddress(), true));
  await (await contract.connect(newOwner).setAnchoringAccount(await newlyAuthorized.getAddress(), true)).wait();
  assert.equal(await contract.isAnchoringAccount(await newlyAuthorized.getAddress()), true);
});

test("different receipt commitments anchor independently and are retrievable", async () => {
  const first = syntheticReceipt("first");
  const second = syntheticReceipt("second");
  const firstId = await contract.computeReceiptId(first);
  const secondId = await contract.computeReceiptId(second);

  await (await contract.connect(authorizedAnchorer).anchorReceipt(first)).wait();
  await (await contract.connect(authorizedAnchorer).anchorReceipt(second)).wait();

  assert.notEqual(firstId, secondId);
  assert.equal(await contract.receiptExists(firstId), true);
  assert.equal(await contract.receiptExists(secondId), true);
  assert.equal((await contract.getReceipt(secondId)).hospitalUpdateCommitment, second.hospitalUpdateCommitment);
});
