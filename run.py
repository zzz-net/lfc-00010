from app import create_app

app = create_app()

if __name__ == '__main__':
    print('=' * 50)
    print('  实验室样本转运台账系统')
    print('  默认账号:')
    print('    管理员: admin / admin123')
    print('    操作员: operator / op123456')
    print('=' * 50)
    app.run(debug=True, host='0.0.0.0', port=5000)
