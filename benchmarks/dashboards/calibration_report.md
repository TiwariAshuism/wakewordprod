# Confidence Calibration Report — 'hey aura'

Held-out (accent-independent) data split in HALF (report rule 2): **calibration accents** = `['en-gb-scotland', 'uk']` (fits a,b / T), **eval accents** = `['en-gb-x-gbclan', 'us']` (before/after metrics; the FA/hr eval set). The two halves share no accent.

Target-class softmax posterior computed exactly like `benchmarks/harness/bench_kws.py:81-83`. Platt = `sigmoid(a*z+b)` on the target logit (primary); Temperature = `softmax(logits/T)` (comparison). Winner = lowest 10-bin ECE that does not degrade AUROC.

**Chosen `method` written to labels.json: `platt`.**

## stage1  (target_index=1)

Calibration clips: 617  |  Eval clips: 627 (pos=105, neg=522).  Fitted: Platt a=2.0790 b=-0.9256; Temperature T=0.9013.

### Before vs after (measured on eval half)

| method | ECE (10-bin) | MCE | Brier | AUROC |
|---|---|---|---|---|
| none (before) | 0.0479 | 0.4618 | 0.0258 | 0.9954 |
| platt | 0.0404 | 0.7565 | 0.0265 | 0.9956 |
| temperature | 0.0461 | 0.4577 | 0.0256 | 0.9954 |

Stage winner (lowest ECE, AUROC not degraded): **platt**.

### Reliability (eval half, uncalibrated vs winner)

```
-- uncalibrated --
  bin        n     conf    acc   gap  reliability(conf=|, acc=#)
  0.0-0.1    470   0.032  0.000  0.032  #|                                      
  0.1-0.2     31   0.132  0.032  0.100   #   |                                  
  0.2-0.3      4   0.251  0.250  0.001            X                             
  0.3-0.4      5   0.327  0.600  0.273               |          #               
  0.4-0.5      2   0.469  0.500  0.031                    | #                   
  0.5-0.6      1   0.538  1.000  0.462                       |                 #
  0.6-0.7      6   0.668  0.500  0.168                      #     |             
  0.7-0.8      7   0.772  0.429  0.343                   #            |         
  0.8-0.9     37   0.860  0.757  0.104                                #   |     
  0.9-1.0     64   0.956  1.000  0.044                                        |#

-- platt --
  bin        n     conf    acc   gap  reliability(conf=|, acc=#)
  0.0-0.1    505   0.011  0.004  0.007  X                                       
  0.1-0.2      6   0.124  0.500  0.376      |               #                   
  0.2-0.3      2   0.244  1.000  0.756           |                             #
  0.3-0.4      6   0.371  0.500  0.129                |     #                   
  0.4-0.5      2   0.455  0.500  0.045                    | #                   
  0.5-0.6     13   0.548  0.308  0.241              #        |                  
  0.6-0.7     19   0.656  0.842  0.186                            |      #      
  0.7-0.8     28   0.749  1.000  0.251                               |         #
  0.8-0.9     20   0.860  1.000  0.140                                    |    #
  0.9-1.0     26   0.970  1.000  0.030                                        |#
```

## stage2  (target_index=1)

Calibration clips: 617  |  Eval clips: 627 (pos=105, neg=522).  Fitted: Platt a=2.7031 b=-1.9836; Temperature T=0.7553.

### Before vs after (measured on eval half)

| method | ECE (10-bin) | MCE | Brier | AUROC |
|---|---|---|---|---|
| none (before) | 0.0390 | 0.4246 | 0.0459 | 0.9791 |
| platt | 0.0325 | 0.5867 | 0.0446 | 0.9834 |
| temperature | 0.0342 | 0.5777 | 0.0481 | 0.9791 |

Stage winner (lowest ECE, AUROC not degraded): **platt**.

### Reliability (eval half, uncalibrated vs winner)

```
-- uncalibrated --
  bin        n     conf    acc   gap  reliability(conf=|, acc=#)
  0.0-0.1    462   0.030  0.009  0.021  #|                                      
  0.1-0.2     37   0.144  0.189  0.045       | #                                
  0.2-0.3     10   0.254  0.400  0.146            |     #                       
  0.3-0.4     13   0.341  0.385  0.043               | #                        
  0.4-0.5      4   0.418  0.000  0.418  #               |                       
  0.5-0.6    0        -      -     -
  0.6-0.7      2   0.629  0.500  0.129                      #    |              
  0.7-0.8      3   0.758  0.333  0.425               #                |         
  0.8-0.9     12   0.852  0.500  0.352                      #             |     
  0.9-1.0     84   0.960  0.917  0.043                                      # | 

-- platt --
  bin        n     conf    acc   gap  reliability(conf=|, acc=#)
  0.0-0.1    500   0.009  0.022  0.013  X                                       
  0.1-0.2     12   0.152  0.250  0.098        |   #                             
  0.2-0.3     12   0.236  0.500  0.264           |          #                   
  0.3-0.4      2   0.308  0.000  0.308  #           |                           
  0.4-0.5      2   0.473  0.500  0.027                    | #                   
  0.5-0.6      1   0.587  0.000  0.587  #                      |                
  0.6-0.7      3   0.691  0.333  0.358               #             |            
  0.7-0.8      4   0.775  0.500  0.275                      #          |        
  0.8-0.9     10   0.861  0.400  0.461                  #                 |     
  0.9-1.0     81   0.969  0.951  0.018                                        X 
```

Reliability diagram (PNG): `calibration_reliability.png`

_Params written into the model's `labels.json` `calibration` block; each stage carries both Platt (a,b) and temperature, and `method` selects which applies. Consumers apply it via `calibrate.apply_calibration` (bench_kws / heym_eval `--calibration`)._
