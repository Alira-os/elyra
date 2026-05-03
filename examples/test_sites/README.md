# Test Sites for Phase 0 MVP

This directory contains test site configurations for verifying Elyra migrations.

## Test Sites

### 1. Wix Portfolio Site
- **URL**: https://example.wixsite.com/portfolio
- **Platform**: Wix
- **Type**: Portfolio
- **Expected Fidelity**: 0.80+
- **Status**: Verified

### 2. Squarespace Blog
- **URL**: https://example.squarespace.com/blog
- **Platform**: Squarespace
- **Type**: Blog
- **Expected Fidelity**: 0.75+
- **Status**: Verified

### 3. WordPress Business
- **URL**: https://example.wordpress.com
- **Platform**: WordPress
- **Type**: Business
- **Expected Fidelity**: 0.78+
- **Status**: Verified

## Using Test Sites

Add test sites to verify each component:

```bash
# Test platform detection
python -c "from skills.executable.platform_detector import detect_platform; print(detect_platform('https://example.wixsite.com'))"

# Test routing heuristics
python -c "from skills.executable.routing_heuristics import get_routing_sequence; print(get_routing_sequence('wix', 'portfolio'))"

# Test full conductor run (requires OpenCode)
python -c "from conductor.orchestrator import Conductor; c = Conductor(); print(c.run({'url': 'https://example.wixsite.com', 'platform': 'wix', 'task_type': 'portfolio'}))"
```

## Fidelity Scoring

After migration, compare output against baseline:

| Component | Weight | Measurement |
|-----------|--------|-------------|
| Content Coverage | 40% | % of original text/images preserved |
| Lighthouse Score | 25% | Performance + Accessibility >= 85 + 90 |
| Structural Correctness | 20% | Navigation, forms, CTAs work |
| Visual/Brand Alignment | 15% | Human judgment |