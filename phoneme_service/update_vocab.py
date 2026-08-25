import sys
import os
import csv

sys.path.insert(0, os.path.abspath('.'))

csv_path = 'data/curated_words.csv'

# Hand-curated IPAs for the missing words
new_words = {
    'toad': 't,oʊ,d', 'tape': 't,eɪ,p', 'dime': 'd,aɪ,m', 'door': 'd,ɔ,r', 'duck': 'd,ʌ,k',
    'dig': 'd,ɪ,ɡ', 'date': 'd,eɪ,t', 'table': 't,eɪ,b,əl', 'puppy': 'p,ʌ,p,i', 'baby': 'b,eɪ,b,i',
    'window': 'w,ɪ,n,d,oʊ', 'wagon': 'w,æ,ɡ,ə,n', 'yard': 'j,ɑ,r,d', 'mommy': 'm,ɑ,m,i', 'man': 'm,æ,n',
    'moon': 'm,u,n', 'nut': 'n,ʌ,t', 'net': 'n,ɛ,t', 'nail': 'n,eɪ,l', 'no': 'n,oʊ',
    'me': 'm,i', 'cake': 'k,eɪ,k', 'gate': 'ɡ,eɪ,t', 'kite': 'k,aɪ,t', 'kid': 'k,ɪ,d',
    'gum': 'ɡ,ʌ,m', 'pack': 'p,æ,k', 'tick': 't,ɪ,k', 'pick': 'p,ɪ,k', 'tag': 't,æ,ɡ',
    'bag': 'b,æ,ɡ', 'big': 'b,ɪ,ɡ', 'rug': 'r,ʌ,ɡ', 'hug': 'h,ʌ,ɡ', 'leg': 'l,ɛ,ɡ',
    'kangaroo': 'k,æ,ŋ,ɡ,ə,r,u', 'brush': 'b,r,ʌ,ʃ', 'wish': 'w,ɪ,ʃ', 'sheet': 'ʃ,i,t', 'shadow': 'ʃ,æ,d,oʊ',
    'shine': 'ʃ,aɪ,n', 'shoulder': 'ʃ,oʊ,l,d,ə,r', 'shovel': 'ʃ,ʌ,v,əl', 'sofa': 's,oʊ,f,ə', 'van': 'v,æ,n',
    'cave': 'k,eɪ,v', 'fork': 'f,ɔ,r,k', 'five': 'f,aɪ,v', 'vase': 'v,eɪ,s', 'sister': 's,ɪ,s,t,ə,r',
    'glass': 'ɡ,l,æ,s', 'grass': 'ɡ,r,æ,s', 'tooth': 't,u,θ', 'math': 'm,æ,θ', 'mother': 'm,ʌ,ð,ə,r',
    'measure': 'm,ɛ,ʒ,ə,r', 'television': 't,ɛ,l,ə,v,ɪ,ʒ,ə,n', 'doll': 'd,ɑ,l', 'wall': 'w,ɔ,l', 'yellow': 'j,ɛ,l,oʊ',
    'light': 'l,aɪ,t', 'lemon': 'l,ɛ,m,ə,n', 'red': 'r,ɛ,d', 'rabbit': 'r,æ,b,ɪ,t', 'ring': 'r,ɪ,ŋ',
    'run': 'r,ʌ,n', 'rope': 'r,oʊ,p', 'rain': 'r,eɪ,n', 'carrot': 'k,æ,r,ə,t', 'robot': 'r,oʊ,b,ɑ,t',
    'parrot': 'p,æ,r,ə,t', 'car': 'k,ɑ,r', 'bear': 'b,ɛ,r', 'dinner': 'd,ɪ,n,ə,r', 'chip': 'tʃ,ɪ,p',
    'church': 'tʃ,ə,r,tʃ', 'check': 'tʃ,ɛ,k', 'chin': 'tʃ,ɪ,n', 'chicken': 'tʃ,ɪ,k,ə,n', 'catch': 'k,æ,tʃ',
    'match': 'm,æ,tʃ', 'beach': 'b,i,tʃ', 'teacher': 't,i,tʃ,ə,r', 'picture': 'p,ɪ,k,tʃ,ə,r', 'jam': 'dʒ,æ,m',
    'jump': 'dʒ,ʌ,m,p', 'jar': 'dʒ,ɑ,r', 'judge': 'dʒ,ʌ,dʒ', 'jacket': 'dʒ,æ,k,ɪ,t', 'giant': 'dʒ,aɪ,ə,n,t',
    'badge': 'b,æ,dʒ', 'page': 'p,eɪ,dʒ', 'magic': 'm,æ,dʒ,ɪ,k', 'spoon': 's,p,u,n', 'smile': 's,m,aɪ,l',
    'snake': 's,n,eɪ,k', 'stop': 's,t,ɑ,p', 'snail': 's,n,eɪ,l', 'space': 's,p,eɪ,s', 'slide': 's,l,aɪ,d',
    'scale': 's,k,eɪ,l', 'clock': 'k,l,ɑ,k', 'flag': 'f,l,æ,ɡ', 'plate': 'p,l,eɪ,t', 'block': 'b,l,ɑ,k',
    'blanket': 'b,l,æ,ŋ,k,ɪ,t', 'clamp': 'k,l,æ,m,p', 'train': 't,r,eɪ,n', 'tree': 't,r,i', 'drum': 'd,r,ʌ,m',
    'grape': 'ɡ,r,eɪ,p', 'bread': 'b,r,ɛ,d', 'crown': 'k,r,aʊ,n', 'green': 'ɡ,r,i,n', 'hand': 'h,æ,n,d',
    'camp': 'k,æ,m,p', 'tent': 't,ɛ,n,t', 'plant': 'p,l,æ,n,t', 'pink': 'p,ɪ,ŋ,k', 'milk': 'm,ɪ,l,k',
    'nest': 'n,ɛ,s,t', 'fast': 'f,æ,s,t', 'desk': 'd,ɛ,s,k', 'bottle': 'b,ɑ,t,əl', 'doggy': 'd,ɔ,ɡ,i',
    'daddy': 'd,æ,d,i', 'kitty': 'k,ɪ,t,i', 'birdie': 'b,ə,r,d,i', 'tub': 't,ʌ,b', 'coat': 'k,oʊ,t',
    'cape': 'k,eɪ,p', 'candy': 'k,æ,n,d,i', 'caterpillar': 'k,æ,t,ə,r,p,ɪ,l,ə,r', 'dinosaur': 'd,aɪ,n,ə,s,ɔ,r',
    'conversation': 'k,ɑ,n,v,ə,r,s,eɪ,ʃ,ə,n', 'understanding': 'ʌ,n,d,ə,r,s,t,æ,n,d,ɪ,ŋ', 'congratulations': 'k,ə,n,ɡ,r,æ,tʃ,ə,l,eɪ,ʃ,ə,n,z',
    'unfortunately': 'ʌ,n,f,ɔ,r,tʃ,ə,n,ə,t,l,i', 'environment': 'ɪ,n,v,aɪ,r,ə,n,m,ə,n,t', 'imagination': 'ɪ,m,æ,dʒ,ə,n,eɪ,ʃ,ə,n',
    'experiment': 'ɪ,k,s,p,ɛ,r,ə,m,ə,n,t', 'certificate': 's,ə,r,t,ɪ,f,ɪ,k,ɪ,t', 'take': 't,eɪ,k',
    
    # additional variants just in case
    'bla': 'b,l,ɑ', 'blu': 'b,l,u', 'fa': 'f,ɑ', 'fee': 'f,i', 'dra': 'd,r,ɑ', 'dri': 'd,r,i'
}

existing_words = set()
with open(csv_path, 'r', encoding='utf-8') as f:
    reader = csv.reader(f)
    next(reader)
    for row in reader:
        if row:
            existing_words.add(row[0].strip().lower())

to_append = []
for w, ipa in new_words.items():
    if w not in existing_words:
        to_append.append([w, ipa])

if to_append:
    with open(csv_path, 'a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(to_append)
    print(f"Successfully appended {len(to_append)} hand-curated words to curated_words.csv")
else:
    print("All hand-curated words are already in the CSV.")
