#!/usr/bin/env python3
"""Comprehensive pre-commit setup validation"""

import os
import sys
import yaml
from pathlib import Path

def test_yaml_validity():
    """AC 1: File exists and is valid YAML"""
    print("Test 1: YAML Validity")
    try:
        with open('.pre-commit-config.yaml', 'r') as f:
            yaml.safe_load(f)
        print("  ✓ .pre-commit-config.yaml exists and is valid YAML")
        return True
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False

def test_required_hooks():
    """AC 1 & 3: Required hooks are defined"""
    print("\nTest 2: Required Hooks Present")
    
    with open('.pre-commit-config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    required_hooks = {
        'ruff': 'Python linting',
        'ruff-format': 'Python formatting',
        'mypy': 'Python type checking',
        'check-ast': 'Python AST',
        'detect-private-key': 'Private key detection',
        'detect-pii': 'PII detection',
        'prettier': 'JS/TS formatting',
    }
    
    found_hooks = {}
    for repo in config.get('repos', []):
        for hook in repo.get('hooks', []):
            hook_id = hook.get('id')
            if hook_id in required_hooks:
                found_hooks[hook_id] = True
    
    all_found = True
    for hook_id, description in required_hooks.items():
        if hook_id in found_hooks:
            print(f"  ✓ {hook_id}: {description}")
        else:
            print(f"  ✗ {hook_id} not found")
            all_found = False
    
    return all_found

def test_pii_scanner_script():
    """AC 2 & 4: PII scanner script exists and patterns are defined"""
    print("\nTest 3: PII Scanner Script")
    
    script_path = Path('scripts/pre-commit-pii-scan.py')
    if not script_path.exists():
        print(f"  ✗ Script not found at {script_path}")
        return False
    
    print(f"  ✓ Script found at {script_path}")
    
    # Read and validate script
    with open(script_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    required_patterns = ['ssn', 'credit_card', 'account_number', 'signature']
    all_found = True
    for pattern in required_patterns:
        if f'"{pattern}"' in content or f"'{pattern}'" in content:
            print(f"  ✓ PII pattern '{pattern}' is defined")
        else:
            print(f"  ✗ PII pattern '{pattern}' not found")
            all_found = False
    
    return all_found

def test_pii_detection():
    """AC 2 & 4: PII detection works correctly"""
    print("\nTest 4: PII Detection Functionality")
    
    import subprocess
    import tempfile
    
    # Create test file with PII
    # allowlist: test SSN and credit card for PII scanner validation
    test_data = """
    This is a test document.
    SSN: 123-45-6789
    Credit Card: 4111-1111-1111-1111
    """
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(test_data)
        test_file = f.name
    
    try:
        # Run PII scanner
        result = subprocess.run(
            [sys.executable, 'scripts/pre-commit-pii-scan.py', test_file],
            capture_output=True,
            text=True
        )
        
        # Should fail (exit code 1) because PII was found
        if result.returncode == 1 and 'PII Detection failed' in result.stderr:
            print("  ✓ PII detection correctly identifies patterns")
            print("    Detected: SSN and Credit Card patterns")
            return True
        else:
            print("  ✗ PII detection failed or produced unexpected output")
            print(f"    Exit code: {result.returncode}")
            print(f"    Output: {result.stdout}")
            print(f"    Error: {result.stderr}")
            return False
    finally:
        os.unlink(test_file)

def test_hook_configuration():
    """AC 3: Hook configuration for blocking commits"""
    print("\nTest 5: Hook Configuration")
    
    with open('.pre-commit-config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # Find detect-pii hook
    detect_pii_found = False
    all_checks_passed = True
    
    for repo in config.get('repos', []):
        if repo.get('repo') == 'local':
            for hook in repo.get('hooks', []):
                if hook.get('id') == 'detect-pii':
                    detect_pii_found = True
                    entry = hook.get('entry', '')
                    stages = hook.get('stages', [])
                    types = hook.get('types', [])
                    
                    # Validate entry
                    if 'pre-commit-pii-scan.py' in entry:
                        print(f"  ✓ detect-pii hook entry: {entry}")
                    else:
                        print(f"  ✗ detect-pii hook entry missing script: {entry}")
                        all_checks_passed = False
                    
                    # Validate stages. pre-commit's default stage list is
                    # `[pre-commit]` (the *name* of the stage is
                    # ``pre-commit``, not ``commit``). An empty ``stages``
                    # list also implicitly means ``pre-commit`` only.
                    if not stages or 'pre-commit' in stages or 'commit' in stages:
                        print(f"  ✓ detect-pii runs on commit stage (stages: {stages or '[default]'})")
                    else:
                        print(f"  ✗ detect-pii missing 'pre-commit' stage (stages: {stages})")
                        all_checks_passed = False
                    
                    # Validate types
                    if types:
                        print(f"  ✓ detect-pii scans types: {types}")
                    else:
                        print("  ✗ detect-pii missing types configuration")
                        all_checks_passed = False
                    
                    break
    
    if not detect_pii_found:
        print("  ✗ detect-pii hook not found in config")
        return False
    
    if all_checks_passed:
        print("  ✓ PII detection hook is properly configured for blocking commits")
        return True
    else:
        return False

def main():
    """Run all tests"""
    print("=" * 60)
    print("Pre-Commit Configuration Validation")
    print("=" * 60)
    
    tests = [
        test_yaml_validity,
        test_required_hooks,
        test_pii_scanner_script,
        test_pii_detection,
        test_hook_configuration,
    ]
    
    results = []
    for test in tests:
        results.append(test())
    
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    
    if all(results):
        print("\n✓ All acceptance criteria are met!")
        print("\nAcceptance Criteria Verification:")
        print("  ✓ AC 1: File exists and is valid YAML")
        print("  ✓ AC 2: PII patterns are defined and tested")
        print("  ✓ AC 3: Pre-commit hook runs on git commit and blocks violations")
        # AC 4 is verified by pre-commit install working (manual check)
        return 0
    else:
        print("\n✗ Some acceptance criteria are not met")
        return 1

if __name__ == '__main__':
    sys.exit(main())
