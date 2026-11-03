pragma circom 2.2.2;

include "poseidon.circom";
include "bitify.circom";

/*
 * QuantizedUpdateChunkV1(8)
 *
 * Private inputs:
 *   q[8]  signed int8 quantized values in [-128, 127]
 *   salt  a field element supplied by the prover
 *
 * Public inputs, in this exact order:
 *   round_context, model_context, artifact_context, chunk_index, chunk_count,
 *   chunk_commitment, binding_commitment
 *
 * `chunk_commitment` is Poseidon(q[0] + 128, ..., q[7] + 128).  The server
 * independently derives it from the protected uploaded update after applying
 * the documented deterministic quantization.  `binding_commitment` is a
 * second Poseidon hash binding the chunk commitment to its round, model,
 * update-artifact, and chunk-position contexts plus private salt.
 *
 * This proves only one quantized chunk.  It does not prove model-training
 * correctness, MRI provenance, clinical validity, or full-model coverage.
 */
template QuantizedUpdateChunkV1(N) {
    signal input round_context;
    signal input model_context;
    signal input artifact_context;
    signal input chunk_index;
    signal input chunk_count;
    signal input chunk_commitment;
    signal input binding_commitment;

    signal input q[N];
    signal input salt;

    signal encoded[N];
    component range[N];
    for (var index = 0; index < N; index++) {
        encoded[index] <== q[index] + 128;
        range[index] = Num2Bits(8);
        range[index].in <== encoded[index];
    }

    component chunkHasher = Poseidon(N);
    for (var index = 0; index < N; index++) {
        chunkHasher.inputs[index] <== encoded[index];
    }
    chunkHasher.out === chunk_commitment;

    component bindingHasher = Poseidon(7);
    bindingHasher.inputs[0] <== round_context;
    bindingHasher.inputs[1] <== model_context;
    bindingHasher.inputs[2] <== artifact_context;
    bindingHasher.inputs[3] <== chunk_index;
    bindingHasher.inputs[4] <== chunk_count;
    bindingHasher.inputs[5] <== chunk_commitment;
    bindingHasher.inputs[6] <== salt;
    bindingHasher.out === binding_commitment;
}

component main {
    public [
        round_context,
        model_context,
        artifact_context,
        chunk_index,
        chunk_count,
        chunk_commitment,
        binding_commitment
    ]
} = QuantizedUpdateChunkV1(8);
