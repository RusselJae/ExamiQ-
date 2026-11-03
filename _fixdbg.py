import re
p = r'apps/users/tests/test_debug_signup.py'
s = open(p, encoding='utf-8').read()
s = s.replace('signup_year_level', 'year_level')
open(p, 'w', encoding='utf-8').write(s)
print('done')
