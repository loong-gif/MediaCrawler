# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。


# 微博平台配置

# 搜索类型，具体的枚举值在media_platform/weibo/field.py中
WEIBO_SEARCH_TYPE = "popular"

# 指定微博ID列表
WEIBO_SPECIFIED_ID_LIST = [
    # "5244917190495532",
# "OzfKKgyhr",
# "QlA2SnnJi",
# "Ql0w9bc2l",
# "Qk3vx9oYL",
# "QjaDiaOHo",
# "QiQv524Us",
# "QiaEnFr8G",
# "QhLXEoksF",
# "Qh0ZEyfUN",
# "QdOmMy68M",
# "QdwFilz4B",
# "Qd4qTo0dm",
# "QcBCyE6ZV",
# "QbR2nkhtJ",
# "QbpNLjljh",
# "QaXJa1AIE"
# "QkXmZAS56",
# "Qkx8tjCWw",
# "QftOz9s8x",
# "Qf1D7CojM",
# "QeQpWxCAg",
# "QduMad6u0",
# "QbPjHcF6H",
# "QaFptAxPf",
# "Q3CYXaDen",
# "Q303dalOK",
# "Q13vL1YkT",
# "Q0Cac5OD9",
# "PFclUkmxJ",
# "PE8Gdy8AO",
# "PC7WOfzlo",
# "PB5G1Cfuk",
# "PAuWrnXlT",
# "PhAJiAnRt",
# "PfCTsgrP9",
# "PchEgdZJa",
# "PbEKwztu7",
# "Par770A3B",
# "PahXB9Mwn",
# "P7SYMyNua",
# "OzFAkrrUU",
# "OyC57tCOq",
# "Oxf2OmS7t",
# "Owtx22Q95",
# "OvHNehRzJ",
# "Ombnfa2iR",
# "Om097h0dl",
# "OkmqJw648",
# "OkaUjmcpz",
# "Oj82oesLJ",
# "OidA33CsP",
# "OhCvgdPiy",
# "NyrymnNxn",
# "Ny9qS3syt",
# "NxQESBgfO",
# "Nx5qggOK9",
# "NvSMFgSVL",
# "NrsEYsVnY",
# "NqnQXksxs"
# "QlT2Gq5Oa",
# "QlqqQqVJy",
# "Ql9ltqacP",
# "QkyaJF2ZS",
# "Qk5V1khN9",
# "QjWqvnh1H",
# "QftQLAXx1",
# "QfdIIDZ0t",
# "QeVaVr2GW",
# "Qe9vNmGwg",
# "QdQKIlXzz",
# "QcDouCbbc",
# "QbE9AiYOV",
# "Qb7xzE7B1",
# "Q9Evoee8P",
# "Q2hcMoRbP",
# "Q14hf8TLm",
# "PDfaVcdlm",
# "PCRTRe1Hj",
# "PCDtz0Tgk",
# "PBQnVpLkm",
# "PBI1fDl6p",
# "PxR9z7L0J",
# "PxsJiyK0N",
# "Pw61Q0sAn",
# "PvBsrpbLf",
# "PvoZv7Q2f",
# "Pv7xLxjvq",
# "Puw0anbdP"
# "QjoY8woHt",
# "QjjeezN7o",
# "QjfgDE9wy",
# "QiXtp741W",
# "Qileq0BID",
# "Qi7lI1LFL",
# "Qc8M7sRDv",
# "Qa26Uc2TM",
# "Qa0M8CJpm",
# "Q9YUbp4hw",
# "Q9Kfe3LX6",
# "Q9dVnqzzz",
# "Q8MfwwvM6",
# "Q8t0Vp9iR",
# "Q7RCGnwma",
# "Q5D1x7qD5",
# "Q5AbT80g4",
# "Q5qDons52",
# "Q5g4HBuzR",
# "Q52BitbuJ",
# "Q4w9BvyLQ",
# "Q4ln9uBKw",
# "Q4h7AyFcg",
# "Q4btpxtG8",
# "Q3sTax3sC",
# "Q1cqAbkl0",
# "Q1auL2mxS",
# "Q10xMmkL1",
# "Q0SKvc8qS",
# "Q0pIt8dOR",
# "Q0pwjCPwT",
# "Q0fVvoAaO",
# "Q0fIaCoiD",
# "Q07yooWCF",
# "PDaxw2day",
# "PD1t495f3",
# "PD16VplaU",
# "PC7ove24k",
# "PC0LeyyBt",
# "PBEcHwbzn",
# "PB5bDnQeG",
# "PAUkZjOFb",
# "PAq3lilK6"
# # zhaojinmai
# "QmbTOv4LL",
# "Qm2neuzUs",
# "QkOh3coTP",
# "QkMbk87ID",
# "QkFQoo7CL",
# "QkFjausEq",
# "QkCwoCzRM",
# "QkkjinVeC",
# "Qkenoci4P",
# "QjV5me5RM",
# "QjU4Cmz0p",
# "QgZc94zvM",
# "QgvKWx1p1",
# "Qf1fubdZb",
# "QeG6ZrmM4",
# "QerkrvD9v",
# "Qc9GX99XF",
# "QbeSfBJZm",
# "Qb6aUjIYo",
# "QaKzp3a6l"
# # yuni

# "Qm22YeKm4",
# "QlhEQFkzt",
# "QfDosaTtW",
# "Q82VC2tTz",
# "Q5Lnfeysn",
# "MD0VzcjsV",
# "MzP4v4RJ5",
# "MtfgSkoXS",
# "MlmQ3EAnZ",
# "Ml4RZxBfd",
# "LbUGxbrtH"

# # vv
# # 根据我从VV宝贝a微博主页提取的所有帖子，这是完整列表：
# "QbDROmeoR", "PzjorEzkc", "OlKRapP4i", "OgJoG3RHm", "OfEpwljkZ", "O9IVXuYTl", "O95IakcLB", "O8nfXq9Eq", "O7UZtvQpG", "O5gDSkwNX", "NyTGEuV1M", "Nyc7UycM1", "Ny2p2EiVU", "NufxJinfz", "NtsW3acgI", "Nt0de40vq", "NqToDtzaz", "NqiS55DMu", "NpZVYgvkp", "Np3dusPgS", "NoiGd44mm", "NneWrllc3", "NndPV6jjs", "NmXk1FDBL", "NmuDj7HqI", "Nmt5Ol9qm", "NmjhLpeCP", "NkYLF2Ce7", "Njr9soel8", "NiwqssBqQ", "Ni9hNdhF4", "NhWhF49hD"
#     # enddme
#     "JED2Sn7J7", "QjN2xexse", "QgfCbzt6m", "Q3h6R8Bki", "Q2FIXqGEJ", "Q2pJ7beA2", "Q27rtDXi1", "PFNUbcJpT", "PFiwXiKAl"
#  "Q2pJ7beA2", "Q27rtDXi1", "PFNUbcJpT", "PFiwXiKAl", "Qdnqy2SfU", "QbGTxoQS6", "QbyQVsIg3", "QaaQBtxNl", "Q9wJYe3QB", "Pz5kFaK3W"
    
# # 哈尼
# "QkXfgo6YE",
# "QkCAb1FHd",
# "QknNK2BSO",
# "QdFQn6yGV",
# "Qd3Ttah8O",
# "QcK4w28oD",
# "QchbmltrE",
# "QbR9ojgfY"

# 根据当前页面（用户：夏天心同学）上所有可见的微博帖子，以下是提取的帖子ID列表（每个ID带引号，用逗号分隔，一行一个）：

# "QkUK6uAex",
# "QkmvA8BDg",
# "Qk3oU7Ezd",
# "QigEakI8h",
# "PAVrXuj7M",
# "Qh0MYaCzk",
# "QgJRG6JeW",
# "Qc2he0wEs",
# "QbK3mmdPc",
# "Q7SWUcfab",
# "Q6LA0k5J9",
# "Q3YJn0uWl",
# "PEsAAvXGl",
# "PAEzIdt6x",
# "Q3mZfeLLb",
# "PF5zemVm8",
# "PwEXxvQcN",
# "PwnNx2GGA"

# "Mco0M1BOf",
# "Qkuo6nr5X",
# "Qjkzaiuwc",
# "QhlJ2blAJ",
# "QgMfcsuh9",
# "QeGS5e0Dx",
# "QdovykZYS",
# "QbcJggCTH",
# "PycY3cZky",
# "Pj9XxizFy",
# "PiemM0Nns",
# "Pi5IpcrHP",
# "Phiwg2nxD",
# "Pe8uldBic",
# 根据当前页面（用户：宋祖儿laraina，UID: 2440179153）上所有可见的微博帖子，以下是提取的帖子ID列表（每个ID带引号，用逗号分隔，一行一个）：

# "QkXT4bdd6",
# "QkdvbgFn5",
# "QjunhARce",
# "Qj8YCjbMX",
# "Qi7qAv2N3",
# "QhWwD0McB",
# "QhKFRevhD",
# "Qhd6xfdSi",
# "QhcFM43D7",
# "QeJPUilKW",
# "QdCx8nk0C",
# "Qdd6BAlLh",
# "QcLVmfWe8",
# "QcBKpz5as",
# "Qb4kY8Yge",
# "QaFuww8IA",
# "JdSZu87dB",
# "Ql5mc7J1J",
# "Qj6Gsd33m",
# "Qj6ERdE2s",
# "QiWoMtdVx",
# "QiNzwoAY9",
# "QiyrdklwG",
# "Qi7m73eIF",
# "QgvLNzsNj",
# "QfLd7jhRa",
# "Qf9ZByrKA",
# "Qf9qu962b",
# "Qf0Rc8iJJ",
# "QeG5Kk1tN",
# "QeqX3p9ZM",
# "QdMrthLJZ",
# "Qdefp7wLY",
# "Qcz0QBqRq",
# "Qbz0MxkBt",
# "Qbl21pPtt",

#tianxiwei
# "PCjuJfUsN",  # 2025-7-22
# "Qlew0dc7u",  # 1-2 11:48
# "QkW7JnFSw",  # 2025-12-31
# "QhqdpoY1u",  # 2025-12-8
# "QhpJsnMAn",  # 2025-12-8
# "QhcFM7k43",  # 2025-12-6
# "Qh7KxcdTn",  # 2025-12-6
# "QgZCG9eHz",  # 2025-12-5
# "QgSs44ep9",  # 2025-12-4
# "QgRC02utw",  # 2025-12-4
# "QgF53x5vb",  # 2025-12-3
# "QeAWLgmJ6",  # 2025-11-19
# "QewULiE1S",  # 2025-11-19
# "QedNzfc1i",  # 2025-11-17
# "QdvX15xCa",  # 2025-11-12
# "Q8tdW7Yj9",  # 2025-10-10
# "Q7QJ2dH5B",  # 2025-10-6
"Q71b55qu5",  # 2025-10-1
"Q6FKn0APr",   # 2025-9-28
"Q6aBYlWIq",   # 2025-9-25
"PCjuJfUsN",   # 2025-7-22
"Qlew0dc7u",   # 1-2 11:48
"QkW7JnFSw",   # 2025-12-31
"QhqdpoY1u",   # 2025-12-8
"QhpJsnMAn",   # 2025-12-8
"QhcFM7k43",   # 2025-12-6
"Qh7KxcdTn",   # 2025-12-6
"QgZCG9eHz",   # 2025-12-5
"QgSs44ep9",   # 2025-12-4
"QgRC02utw",   # 2025-12-4
"QgF53x5vb",   # 2025-12-3
"QeAWLgmJ6",   # 2025-11-19
"QewULiE1S",   # 2025-11-19
"QedNzfc1i",   # 2025-11-17
"QdvX15xCa",   # 2025-11-12
"Q8tdW7Yj9",   # 2025-10-10
"Q7QJ2dH5B",   # 2025-10-6
"Q71b55qu5",   # 2025-10-1
]

# 指定微博用户ID列表
WEIBO_CREATOR_ID_LIST = [
#    "5372502779",  
# "5680343342",  
"7564215987",  
# "7746040822",  
# "5292770234",  
# "2137467973",  
# "1742568455",  
# "6124633386",  
# "5417332149",  
# "5978764601",  
# "3853697130",  
# "5936171972",  
# "3932588380",  
# "2731935637",  
# "2616380702",  
# "1353112775",  
# "5331040243",  
# "6011499980",  
# "5596373316",  
# "5749071359",  
# "1705586121",  
# "5598574734",  
# "6634214154",  
# "5996184614",  
# "1149714543",  
# "3477715953",  
# "1713031610",  
# "2178928074",  
# "5503575607",  
# "1350995007",  
# "2449552120",  
# "1669879400",  
# "2106192855",  #zjm
# "7930404930",  #夏天心
# "5124641655",  #宋祖儿
# "2440179153",  
    # "3669102477", #鞠婧祎
    # ........................
]
