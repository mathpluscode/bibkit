# bibtidy

A Claude Code skill that verifies the *content* of each bib entry — not just that your `\cite` keys match — catching wrong authors, wrong years, stale arXiv preprints, and incorrect page ranges.

## Install

From the plugin marketplace:
```
/plugin marketplace add mathpluscode/bibtidy
/plugin install bibtidy@bibtidy
```

Or manually:
```bash
cp -r plugins/bibtidy/skills/bibtidy ~/.claude/skills/
```

## Usage

```
/bibtidy refs.bib
```

bibtidy searches Google Scholar and CrossRef for each entry, fixes errors, and upgrades stale preprints to published versions. Non-trivial changes (wrong authors, venue, year, preprint upgrades) include the original entry commented out above so you can compare or revert; minor formatting fixes (page hyphens, DOI prefixes) are applied silently. We recommend using git to track changes.

To remove bibtidy comments after review, just ask Claude: "remove all bibtidy comments from refs.bib"

## Examples

**Example 1**: Google Scholar adds editors as co-authors.

Before:
```bibtex
@article{hyvarinen2005estimation,
  title={Estimation of non-normalized statistical models by score matching.},
  author={Hyv{\"a}rinen, Aapo and Dayan, Peter},
  journal={Journal of Machine Learning Research},
  volume={6},
  number={4},
  year={2005}
}
```

After:
```bibtex
% @article{hyvarinen2005estimation,
%   title={Estimation of non-normalized statistical models by score matching.},
%   author={Hyv{\"a}rinen, Aapo and Dayan, Peter},
%   journal={Journal of Machine Learning Research},
%   volume={6},
%   number={4},
%   year={2005}
% }
% bibtidy: source https://jmlr.org/papers/v6/hyvarinen05a.html
% bibtidy: removed "Dayan, Peter" — journal editor, not co-author
@article{hyvarinen2005estimation,
  title={Estimation of non-normalized statistical models by score matching},
  author={Hyv{\"a}rinen, Aapo},
  journal={Journal of Machine Learning Research},
  volume={6},
  number={4},
  year={2005}
}
```

**Example 2**: arXiv preprint upgraded to published version.

Before:
```bibtex
@article{lipman2022flow,
  title={Flow matching for generative modeling},
  author={Lipman, Yaron and Chen, Ricky TQ and Ben-Hamu, Heli and Nickel, Maximilian and Le, Matt},
  journal={arXiv preprint arXiv:2210.02747},
  year={2022}
}
```

After:
```bibtex
% @article{lipman2022flow,
%   title={Flow matching for generative modeling},
%   author={Lipman, Yaron and Chen, Ricky TQ and Ben-Hamu, Heli and Nickel, Maximilian and Le, Matt},
%   journal={arXiv preprint arXiv:2210.02747},
%   year={2022}
% }
% bibtidy: source https://openreview.net/forum?id=PqvMRDCJT9t
% bibtidy: published at ICLR 2023 (was arXiv preprint)
@inproceedings{lipman2022flow,
  title={Flow matching for generative modeling},
  author={Lipman, Yaron and Chen, Ricky TQ and Ben-Hamu, Heli and Nickel, Maximilian and Le, Matt},
  booktitle={International Conference on Learning Representations},
  year={2023}
}
```

**Example 3**: bioRxiv preprint duplicated with published version.

Before:
```bibtex
@article{watson2022broadly,
  title={Broadly applicable and accurate protein design by integrating structure prediction networks and diffusion generative models},
  author={Watson, Joseph L and Juergens, David and Bennett, Nathaniel R and Trippe, Brian L and Yim, Jason and Eisenach, Helen E and Ahern, Woody and Borst, Andrew J and Ragotte, Robert J and Milles, Lukas F and others},
  journal={BioRxiv},
  pages={2022--12},
  year={2022},
  publisher={Cold Spring Harbor Laboratory}
}

@article{watson2023novo,
  title={De novo design of protein structure and function with RFdiffusion},
  author={Watson, Joseph L and Juergens, David and Bennett, Nathaniel R and Trippe, Brian L and Yim, Jason and Eisenach, Helen E and Ahern, Woody and Borst, Andrew J and Ragotte, Robert J and Milles, Lukas F and others},
  journal={Nature},
  volume={620},
  pages={1089--1100},
  year={2023},
  publisher={Nature Publishing Group UK London}
}
```

After:
```bibtex
% bibtidy: DUPLICATE of watson2023novo — consider removing
@article{watson2022broadly,
  title={Broadly applicable and accurate protein design by integrating structure prediction networks and diffusion generative models},
  author={Watson, Joseph L and Juergens, David and Bennett, Nathaniel R and Trippe, Brian L and Yim, Jason and Eisenach, Helen E and Ahern, Woody and Borst, Andrew J and Ragotte, Robert J and Milles, Lukas F and others},
  journal={BioRxiv},
  pages={2022--12},
  year={2022},
  publisher={Cold Spring Harbor Laboratory}
}

@article{watson2023novo,
  title={De novo design of protein structure and function with RFdiffusion},
  author={Watson, Joseph L and Juergens, David and Bennett, Nathaniel R and Trippe, Brian L and Yim, Jason and Eisenach, Helen E and Ahern, Woody and Borst, Andrew J and Ragotte, Robert J and Milles, Lukas F and others},
  journal={Nature},
  volume={620},
  pages={1089--1100},
  year={2023},
  publisher={Nature Publishing Group UK London}
}
```

## License

MIT
