# Claw 项目目录说明
# 确保domain目录被识别为Python包

"""
项目已完成DDD架构迁移,目录结构:
- domain: 领域层(核心业务)
- infrastructure: 基础设施层(待迁移)
- api: API层
- application: 应用层(待迁移)
"""

# 此文件确保项目根目录被识别为Python包根
# pytest会自动识别此目录为包根,允许导入domain等模块
