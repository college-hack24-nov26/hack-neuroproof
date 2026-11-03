"""Custom federated-learning coordinator domain.

This module intentionally has no Flower runtime dependency.  It records
coordinator metadata only; private training data, update tensors, witnesses,
and proof material remain outside PostgreSQL and HTTP request bodies.
"""
