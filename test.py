student = {
    'name': 'Иван',
    'score': 0
}

olympiad = [student.copy()]
excellent = [student.copy()]

olympiad[0]['score'] = 95

print(f'{olympiad=}')

excellent[0]['score'] = 70

print(f'{excellent=}')

print(f'{olympiad=}')