"use strict";

const crypto = require("node:crypto");
const { ethers } = require("ethers");
const { compileAnchor } = require("./compile.cjs");

function requiredRpcUrl() {
  const index = process.argv.indexOf("--rpc-url");
  const value = index >= 0 ? process.argv[index + 1] : undefined;
  if (!value || !value.startsWith("http://127.0.0.1:")) {
    throw new Error("A loopback --rpc-url is required for the synthetic deployment helper.");
  }
  return value;
}

function commitment(label) {
  return ethers.keccak256(ethers.toUtf8Bytes(`synthetic-step-164:${label}`));
}

async function main() {
  const rpcUrl = requiredRpcUrl();
  const provider = new ethers.JsonRpcProvider(rpcUrl, { chainId: 31337, name: "hardhat" }, { staticNetwork: true });
  const [deployer, anchorer] = await Promise.all([provider.getSigner(0), provider.getSigner(1)]);
  const compiled = compileAnchor();
  const factory = new ethers.ContractFactory(compiled.abi, compiled.bytecode, deployer);
  const contract = await factory.deploy(await anchorer.getAddress());
  await contract.waitForDeployment();

  const input = {
    federationRoundCommitment: commitment("round"),
    modelVersionCommitment: commitment("model"),
    hospitalUpdateCommitment: commitment("update"),
    proofArtifactSha256: commitment("proof"),
    verificationKeyId: commitment("verification-key"),
  };
  const receiptId = await contract.computeReceiptId(input);
  const transaction = await contract.connect(anchorer).anchorReceipt(input);
  const transactionReceipt = await transaction.wait();
  const contractAddress = await contract.getAddress();
  const runtimeCode = await provider.getCode(contractAddress);
  const network = await provider.getNetwork();

  process.stdout.write(`${JSON.stringify({
    chainId: Number(network.chainId),
    contractAddress,
    runtimeCodeSha256: crypto.createHash("sha256").update(Buffer.from(runtimeCode.slice(2), "hex")).digest("hex"),
    receiptId,
    anchorTransactionHash: transaction.hash,
    anchorBlockNumber: Number(transactionReceipt.blockNumber),
    commitments: input,
  })}\n`);
}

main().catch((error) => {
  process.stderr.write(`Synthetic anchor setup failed: ${error.message}\n`);
  process.exitCode = 1;
});
