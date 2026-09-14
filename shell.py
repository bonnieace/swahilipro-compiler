import time

try:
    import swahilipro.swahilipro as swahilipro
except ImportError:
    import swahilipro

ascii_art = [
    [
        "   ____",
        " / ___|",
        "| |___ ",
        " \\___ \\",
        "  ___)|",
        " |____/"
    ],
    [
        "  _    _ ",
        " | |  | |",
        " | |  | |",
        " | |/\\| |",
        " \\  /\\  /",
        "  \\/  \\/ "
    ],
    [
        "   ____   ",
        "  / __ \\ ",
        " / / _` |",
        "| | (_| |",
        " \\ \\__,_|",
        "  \\____/ "
    ],
    [
        "_      ",
        "| |     ",
        "| |___  ",
        "|  __ | ",
        "| | | | ",
        "|_| |_| "
    ],
    [
        " _  ",
        "| | ",
        "| | ",
        "| | ",
        "| | ",
        "|_| "
    ],
    [
        " _    ",
        "| |   ",
        "| |   ",
        "| |   ",
        "| |__ ",
        "|____|"
    ],
    [
        " _  ",
        "| | ",
        "| | ",
        "| | ",
        "| | ",
        "|_| "
    ]
]


def print_ascii_art(art):
    for i in range(len(art[0])):
        line = "".join([art[j][i] for j in range(len(art))])
        print(line)
        time.sleep(0.1)


print_ascii_art(ascii_art)
while True:
    text = input("SWAHILI > ")
    result, error = swahilipro.run("<stdin>", text)

    if error:
        print(error.as_string())
    elif result is not None:
        print(result)
