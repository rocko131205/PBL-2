def generate_key_matrix(key):
    key = key.upper().replace( "J", "I")
    matrix=[]
    used=set()

    for ch in key:
        if ch.isalpha() and ch not in used:
            used.add(ch)
            matrix.append(ch)
        else:
            print("Capital only")
    for ch in "ABCDEFGHIKLMNOPQRSTUVWXYZ":
        if ch not in used:
            used.add(ch)
            matrix.append(ch)
    return [matrix[i:i + 5] for i in range(0, 25, 5)]


def display_key_matrix(matrix):
    for row in matrix:
        print("".join(row))
        print()





def find_position(matrix,ch):
    for r in range(5):
        for c in range(5):
            if matrix[r][c]==ch:
                return (r,c)






def Pre_Process_Input(key):
    text=text.upper().replace("J","I")
    text="".join(ch for ch in text if ch.isalpha())


    diagraph =[]
    i=0
    while i < len(text):
        first = text[i]

        # If last character is alone, add X
        if i + 1 == len(text):
            digraphs.append(first + "X")
            break

        second = text[i + 1]

        # If both letters are same, insert X
        if first == second:
            digraphs.append(first + "X")
            i += 1
        else:
            digraphs.append(first + second)
            i += 2

    return digraphs
    while key != []:
            string.append(key[:2])
            key = string[2:]
    return string
def pre_process_ciphered_text(text):
    text = text.upper().replace("J", "I")
    text = "".join(ch for ch in text if ch.isalpha())
    return [text[i:i + 2] for i in range(0, len(text), 2)]


def encryption(text, key):
    matrix=generate_key_matrix(key)
    diagraph=Pre_Process_Input(text)
    ciphertext=""
    for pair in diagraph:
        a, b = pair[0], pair[1]
        r1, c1= find_position(matrix, a)
        r2, c2= find_position(matrix, b)
        if r1 == r2:
            ciphertext += matrix[r1][(c1 + 1) % 5]
            ciphertext += matrix[r2][(c2 + 1) % 5]




        elif r1 == r2:
            ciphertext += matrix[(r1 + 1) % 5][c1]
            ciphertext += matrix[(r2 + 1) % 5][c2]
        else:
            ciphertext += matrix[r1][c1]
            ciphertext += matrix[r2][c2]
    return ciphertext, matrix
def decryption(matrix, key):
    matrix=generate_key_matrix(matrix)
    key=Pre_Process_Input(key)

    digraphs = preprocess_ciphertext(ciphertext)
    plaintext = ""
    for pair in digraphs:
        a, b = pair[0], pair[1]
        r1, c1 = find_position(matrix, a)
        r2, c2 = find_position(matrix, b)

        # Rule 1: Same row -> move left
        if r1 == r2:
            plaintext += matrix[r1][(c1 - 1) % 5]
            plaintext += matrix[r2][(c2 - 1) % 5]

        # Rule 2: Same column -> move up
        elif c1 == c2:
            plaintext += matrix[(r1 - 1) % 5][c1]
            plaintext += matrix[(r2 - 1) % 5][c2]

        # Rule 3: Rectangle -> swap columns
        else:
            plaintext += matrix[r1][c2]
            plaintext += matrix[r2][c1]

    return plaintext, matrix


def main():
    key=input("Enter your key:").strip()

    text = input("Enter you plan text (to be encrypted):")

    while True:





if __name__=="__main__":
    main()