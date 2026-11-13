export const sampleQuest = {
  title: 'Venus and Adonis',
  source: {
    label: 'Thomas Bulfinch, The Age of Fable',
    url: 'https://www.gutenberg.org/ebooks/4925',
  },
  stages: [
    {
      id: 'the-warning',
      title: 'A Warning in the Woods',
      passage: 'One day, Venus, the goddess of love, was playing with her son Cupid when one of his arrows pricked her. The wound seemed small, but before it healed, she met a young hunter named Adonis and fell in love with him. Soon she was spending her days in the woods with Adonis. She was happy to chase a hare or a deer beside him, but when she found signs of wolves or bears, she turned away. Before leaving for Cyprus in a chariot pulled by swans, she urged Adonis to do the same. She would rather see him come home safely than hear of a glorious hunt.',
      question: {
        title: 'Main Idea',
        prompt: 'Which statement best sums up this part of the story?',
        options: [
          'Venus asks Adonis to leave the woods and travel to Cyprus with her.',
          'Venus enjoys hunting with Adonis and urges him to avoid dangerous animals.',
          'Venus wants Adonis to prove his courage by taking on more dangerous animals.',
        ],
      },
    },
    {
      id: 'the-hunt',
      title: 'The Wild Boar',
      passage: 'Venus had warned Adonis that an animal armed with claws or tusks would care little about how brave its hunter was. Adonis did not heed her warning. When his dogs drove a wild boar out of its hiding place, he threw his spear. The spear wounded the boar, but the animal pulled it free with its jaws. Adonis ran as soon as the boar charged. It caught up with him in the open and struck him with its tusks.',
      question: {
        title: 'Vocabulary in Context',
        prompt: 'In the sentence “Adonis did not heed her warning,” what does “heed” mean?',
        options: ['Repeat it to someone else', 'Ask for more details about it', 'Take it seriously and act on it'],
      },
    },
    {
      id: 'the-windflower',
      title: 'The Windflower',
      passage: 'Venus was still in the air when she heard Adonis cry out. She turned the swans around and hurried back, but by the time she landed, Adonis was dead. Venus grieved beside him. She could do nothing to bring him back, but she decided that something would remain to mark his life. She poured nectar over the blood that had fallen on the ground. Soon a red flower opened where he had lain. It was an anemone, sometimes called a windflower. In the story, the same wind that helps the flower open also scatters its petals. The bloom is brief, but the flower returns in its season. Each new bloom gives Venus a way to remember Adonis long after their last hunt.',
      question: {
        title: 'Sentence Puzzle',
        prompt: 'Venus turned her chariot around _____ she heard Adonis cry out.',
        options: ['because', 'unless', 'although'],
      },
    },
  ],
}
