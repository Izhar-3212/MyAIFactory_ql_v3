from specforge_v3.tools.test_runner import run_acceptance_tests

# CrewAI Tools use .run() method
result = run_acceptance_tests.run(
    code='def hello(): return "world"',
    acceptance_criteria=['function returns a string'],
    language='python'
)
print("✅ Test Status:", result['status'])
print("✅ Tests Passed:", result['tests_passed'])
